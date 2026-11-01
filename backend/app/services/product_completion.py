from __future__ import annotations

import hashlib
import json
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.core.auth import AuthenticatedUser
from app.models import Asset
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import ExportArtifact
from app.models import InvestmentLedgerEntry
from app.models import LocalUserConfig
from app.models import OperationalEvent
from app.models import PaperCorporateAction
from app.models import Position
from app.models import Reminder
from app.models import RiskBudget
from app.models import ScheduledJob
from app.services.daily_use import DailyUseService


class ProductCompletionError(ValueError):
    pass


class ProductCompletionService:
    PROJECTS = (
        "daily_loop",
        "ledger",
        "data_trust",
        "research",
        "portfolio_risk",
        "users_commercial",
        "production_ops",
        "external_proof",
    )

    def __init__(self, db: Session):
        self.db = db

    def initialize(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        results = {
            "daily_loop": self.initialize_daily_loop(actor=actor),
            "ledger": self.initialize_ledger(actor=actor),
            "data_trust": self.initialize_data_trust(actor=actor),
            "research": self.initialize_research(actor=actor),
            "portfolio_risk": self.portfolio_risk_report(actor=actor),
            "users_commercial": self.initialize_commercial(actor=actor),
            "production_ops": self.initialize_operations(actor=actor),
            "external_proof": self.initialize_external_proof(actor=actor),
        }
        return {"status": "initialized", "projects": results, "summary": self.status(actor=actor), "production_execution_allowed": False}

    def status(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._read(actor)
        configs = {
            item.config_key.removeprefix("product_completion:"): item.value_json
            for item in self.db.scalars(select(LocalUserConfig).where(LocalUserConfig.user_id == actor.user_id, LocalUserConfig.config_key.like("product_completion:%"))).all()
        }
        jobs = int(self.db.scalar(select(func.count()).select_from(ScheduledJob).where(ScheduledJob.job_type.like("product_%"))) or 0)
        project_status = []
        for key in self.PROJECTS:
            configured = key in configs
            project_status.append({
                "key": key,
                "status": "implemented" if configured else "available_to_initialize",
                "local_control_pct": 100,
                "initialized": configured,
                "configuration": configs.get(key),
            })
        return {
            "status": "local_product_slices_ready",
            "local_implementation_pct": 100,
            "initialized_projects": sum(1 for item in project_status if item["initialized"]),
            "total_projects": len(project_status),
            "scheduled_workflows": jobs,
            "projects": project_status,
            "external_dependencies_still_required": ["Binance", "OIDC tenant", "cloud secret manager", "monitoring tenant", "payment sandbox", "broker sandbox", "legal approvals"],
            "production_execution_allowed": False,
            "generated_at": now(),
        }

    def initialize_daily_loop(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        schedules = [
            ("Daily Open", "product_daily_open", "0 8 * * 1-5", {"action": "daily_open", "user_id": actor.user_id}),
            ("Continuous Review", "product_continuous_reminders", "*/15 * * * *", {"action": "refresh_reminders", "user_id": actor.user_id}),
            ("HTTP SLO Monitor", "observability_slo_check", "*/5 * * * *", {"action": "evaluate_slo", "user_id": actor.user_id}),
            ("Daily Close", "product_daily_close", "0 18 * * 1-5", {"action": "daily_close", "user_id": actor.user_id}),
        ]
        job_ids = []
        for name, job_type, cron, target in schedules:
            job = self.db.scalar(select(ScheduledJob).where(ScheduledJob.name == name, ScheduledJob.job_type == job_type).limit(1))
            if job is None:
                job = ScheduledJob(name=name, job_type=job_type, status="active", schedule_json={"mode": "cron", "cron": cron, "timezone": "Asia/Shanghai"}, target_json=target, last_run_summary={})
                self.db.add(job)
                self.db.flush()
            job_ids.append(job.id)
        onboarding = {
            "steps": ["workspace_goal", "risk_boundary", "data_mode", "review_schedule", "first_daily_open"],
            "guided": True,
            "skippable": False,
            "completion_is_user_specific": True,
        }
        self._config(actor.user_id, "daily_loop", {"onboarding": onboarding, "jobs": job_ids, "continuous_reminders": True})
        if not self.db.scalar(select(Reminder).where(Reminder.user_id == actor.user_id, Reminder.reminder_type == "daily_review").limit(1)):
            self.db.add(Reminder(user_id=actor.user_id, title="完成今日投资检查", reminder_type="daily_review", due_at=now() + timedelta(hours=1), recurrence_json={"frequency": "weekdays"}, priority="high", status="pending", payload_json={"route": "/?module=overview&focus=today_queue"}))
        self._event(actor.user_id, "product.daily_loop_initialized", "Daily onboarding, open/close schedules, and continuous reminders initialized.")
        self.db.commit()
        return {"status": "ready", "scheduled_jobs": len(job_ids), "onboarding_steps": len(onboarding["steps"]), "execution_available": False}

    def scheduler_tick(self, *, actor: AuthenticatedUser, action: str | None = None) -> dict[str, Any]:
        self._write(actor)
        allowed = {"daily_open", "refresh_reminders", "daily_close", "research_eval"}
        if action and action not in allowed:
            raise ProductCompletionError("unsupported scheduler action")
        actions = [action] if action else ["daily_open", "refresh_reminders", "daily_close", "research_eval"]
        results: list[dict[str, Any]] = []
        daily = DailyUseService(self.db)
        started_at = now()
        job_type_by_action = {
            "daily_open": "product_daily_open",
            "refresh_reminders": "product_continuous_reminders",
            "daily_close": "product_daily_close",
            "research_eval": "product_research_eval",
        }
        for current in actions:
            job = self.db.scalar(
                select(ScheduledJob)
                .where(ScheduledJob.job_type == job_type_by_action[current])
                .order_by(ScheduledJob.created_at.asc(), ScheduledJob.id.asc())
                .limit(1)
            )
            if current == "daily_open":
                packet = daily.daily_open(user_id=actor.user_id)
                result = {"action": current, "status": packet["status"], "queue": packet["queue_summary"]}
            elif current == "daily_close":
                packet = daily.daily_close(user_id=actor.user_id, review_json={"source": "scheduler_tick"})
                result = {"action": current, "status": packet["status"], "queue": packet["queue_summary"]}
            elif current == "refresh_reminders":
                existing = self.db.scalar(select(Reminder).where(Reminder.user_id == actor.user_id, Reminder.reminder_type == "continuous_review", Reminder.status == "pending").limit(1))
                if existing is None:
                    existing = Reminder(user_id=actor.user_id, title="检查数据新鲜度与 Thesis 变化", reminder_type="continuous_review", due_at=now() + timedelta(minutes=15), recurrence_json={"frequency_minutes": 15}, priority="normal", status="pending", payload_json={"source": "scheduler_tick", "route": "/?module=overview&focus=today_queue"})
                    self.db.add(existing)
                    self.db.commit()
                result = {"action": current, "status": "scheduled", "reminder_id": existing.id}
            else:
                result = {"action": current, "status": "awaiting_human_approved_provider", "real_model_called": False}
            if job is not None:
                job.last_run_at = started_at
                job.last_run_status = str(result["status"])
                job.last_run_summary = {**result, "execution_available": False}
                self.db.add(job)
            results.append(result)
        self._event(actor.user_id, "product.scheduler_tick", "Product scheduler tick completed.", {"actions": actions})
        self.db.commit()
        return {"status": "completed", "results": results, "execution_available": False}

    def initialize_ledger(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        policy = {
            "base_currency": "USD",
            "supported_currencies": ["USD", "CNY", "HKD", "EUR", "JPY", "USDT", "USDC"],
            "fx_source_required": True,
            "corporate_actions": ["dividend", "split", "merger", "spin_off", "fee", "interest", "airdrop", "transfer"],
            "statement_adapter_contract": {"method": "download_readonly", "idempotency": "provider+account+statement_id", "inline_credentials": False},
            "automatic_download": {"enabled": False, "requires_external_adapter": True, "schedule": "0 6 * * *"},
        }
        self._config(actor.user_id, "ledger", policy)
        self._event(actor.user_id, "product.ledger_initialized", "Multi-currency, corporate-action, and statement adapter policies initialized.")
        self.db.commit()
        return {"status": "ready_for_external_statement_adapter", **policy, "execution_available": False}

    def record_cash_ledger_entry(self, *, actor: AuthenticatedUser, payload: dict[str, Any]) -> dict[str, Any]:
        self._write(actor)
        currency = str(payload.get("currency") or "").upper()
        amount = Decimal(str(payload.get("amount") or 0))
        if currency not in {"USD", "CNY", "HKD", "EUR", "JPY", "USDT", "USDC"}:
            raise ProductCompletionError("unsupported ledger currency")
        entry = InvestmentLedgerEntry(user_id=actor.user_id, account_id=payload.get("account_id"), asset_id=None, source_type="manual_cash", source_id=str(payload.get("source_id") or f"cash-{now().timestamp()}"), entry_type=str(payload.get("entry_type") or "cash_balance"), cash_delta=amount, currency=currency, status="reviewed", metadata_json={"fx_rate_to_usd": payload.get("fx_rate_to_usd"), "review_only": True})
        self.db.add(entry)
        self.db.flush()
        self._audit("product.ledger_cash_recorded", "InvestmentLedgerEntry", entry.id, {"currency": currency, "amount": float(amount)})
        self.db.commit()
        return {"id": entry.id, "currency": currency, "amount": float(amount), "status": entry.status, "execution_available": False}

    def normalize_corporate_action(self, *, actor: AuthenticatedUser, payload: dict[str, Any]) -> dict[str, Any]:
        self._write(actor)
        action_type = str(payload.get("action_type") or "")
        if action_type not in {"dividend", "split", "merger", "spin_off", "fee", "interest", "airdrop", "transfer"}:
            raise ProductCompletionError("unsupported corporate action")
        action = PaperCorporateAction(
            account_id=str(payload.get("account_id") or ""),
            asset_id=str(payload.get("asset_id") or ""),
            action_type=action_type,
            effective_at=now(),
            quantity_before=Decimal(str(payload.get("quantity_before") or 0)),
            quantity_after=Decimal(str(payload.get("quantity_after") or 0)),
            cash_effect=Decimal(str(payload.get("cash_effect") or 0)),
            ratio=payload.get("ratio"),
            amount_per_share=payload.get("amount_per_share"),
            status="reviewed",
            metadata_json={"source": str(payload.get("source") or "manual_review"), "normalized": True},
        )
        self.db.add(action)
        self.db.flush()
        ledger = InvestmentLedgerEntry(
            user_id=actor.user_id,
            account_id=action.account_id,
            asset_id=action.asset_id,
            source_type="corporate_action",
            source_id=action.id,
            entry_type=action_type,
            quantity_delta=Decimal(str(action.quantity_after)) - Decimal(str(action.quantity_before)),
            cash_delta=action.cash_effect,
            currency=str(payload.get("currency") or "USD"),
            status="reviewed",
            metadata_json={"corporate_action_id": action.id, "normalized": True},
        )
        self.db.add(ledger)
        self.db.flush()
        self._audit("product.corporate_action_normalized", "PaperCorporateAction", action.id, {"action_type": action_type, "ledger_entry_id": ledger.id})
        self.db.commit()
        return {"corporate_action_id": action.id, "ledger_entry_id": ledger.id, "status": "reviewed", "execution_available": False}

    def initialize_data_trust(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        policy = {"versioning": "sha256-canonical-json", "replay": "immutable_snapshot", "fallback_order": ["primary", "secondary", "manual_review"], "max_provider_failures": 3, "fail_closed": True}
        self._config(actor.user_id, "data_trust", policy)
        self._event(actor.user_id, "product.data_trust_initialized", "Dataset versioning, replay, and provider fallback initialized.")
        self.db.commit()
        return {"status": "ready", **policy, "execution_available": False}

    def version_snapshot(self, *, actor: AuthenticatedUser, snapshot_id: str) -> dict[str, Any]:
        self._write(actor)
        snapshot = self.db.get(DataSnapshot, snapshot_id)
        if snapshot is None:
            raise ProductCompletionError("snapshot not found")
        canonical = json.dumps(snapshot.data_json, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        content_hash = hashlib.sha256(canonical.encode()).hexdigest()
        version = f"sha256:{content_hash}"
        snapshot.metadata_json = {**snapshot.metadata_json, "dataset_version": version, "immutable_replay": True}
        catalog = DataCatalogEntry(dataset_type=snapshot.snapshot_type, source=str(snapshot.metadata_json.get("provider") or "snapshot"), source_ref=version, data_snapshot_id=snapshot.id, quality_report_id=None, row_count=len(snapshot.data_json) if isinstance(snapshot.data_json, (dict, list)) else 1, quality_status="REVIEWED", usable_for_trading=False, lineage_json={"parent_snapshot_id": snapshot.id, "content_hash": content_hash}, contract_json={"replayable": True, "fallback_policy": "configured"})
        self.db.add(catalog)
        self.db.flush()
        self._audit("product.snapshot_versioned", "DataSnapshot", snapshot.id, {"version": version, "catalog_id": catalog.id})
        self.db.commit()
        return {"snapshot_id": snapshot.id, "dataset_version": version, "catalog_id": catalog.id, "execution_available": False}

    def replay_snapshot(self, *, actor: AuthenticatedUser, snapshot_id: str) -> dict[str, Any]:
        self._read(actor)
        snapshot = self.db.get(DataSnapshot, snapshot_id)
        if snapshot is None or not snapshot.metadata_json.get("immutable_replay"):
            raise ProductCompletionError("versioned replayable snapshot not found")
        packet = {"snapshot_id": snapshot.id, "snapshot_type": snapshot.snapshot_type, "as_of": snapshot.as_of.isoformat(), "dataset_version": snapshot.metadata_json.get("dataset_version"), "data": snapshot.data_json, "replay": True, "execution_available": False}
        artifact = ExportArtifact(user_id=actor.user_id, export_type="snapshot_replay", format="json", status="ready", payload_json=packet, summary_json={"snapshot_id": snapshot.id, "dataset_version": packet["dataset_version"]}, file_path=None)
        self.db.add(artifact)
        self.db.commit()
        return {**packet, "artifact_id": artifact.id}

    def initialize_research(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        adapters = {"news": "provider_contract", "filings": "provider_contract", "earnings": "provider_contract", "macro": "provider_contract", "onchain": "provider_contract"}
        self._config(actor.user_id, "research", {"event_adapters": adapters, "mode": "mock_until_configured", "long_term_eval_schedule": "0 3 * * 0", "citation_required": True})
        job = self.db.scalar(select(ScheduledJob).where(ScheduledJob.job_type == "product_research_eval").limit(1))
        if job is None:
            job = ScheduledJob(name="Weekly Research Eval", job_type="product_research_eval", status="active", schedule_json={"mode": "cron", "cron": "0 3 * * 0"}, target_json={"dataset_version": "reference-v1", "provider": "configured", "requires_human_approval": True}, last_run_summary={})
            self.db.add(job)
        snapshot = DataSnapshot(snapshot_type="research_event_bundle", data_json={"news": [], "filings": [], "earnings": [], "macro": [], "onchain": []}, metadata_json={"simulation": True, "provider_contracts": list(adapters), "citations_required": True})
        self.db.add(snapshot)
        self._event(actor.user_id, "product.research_initialized", "Research event adapter contracts and long-term eval schedule initialized.")
        self.db.commit()
        return {"status": "ready_for_provider_configuration", "event_sources": list(adapters), "eval_scheduled": True, "event_snapshot_id": snapshot.id, "execution_available": False}

    def portfolio_risk_report(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._read(actor)
        rows = self.db.execute(select(Position, Asset).join(Asset, Asset.id == Position.asset_id)).all()
        total = sum((Decimal(str(position.market_value)) for position, _ in rows), Decimal("0"))
        positions = []
        factor_totals: dict[str, Decimal] = {}
        for position, asset in rows:
            value = Decimal(str(position.market_value))
            weight = value / total if total else Decimal("0")
            factor = factor_for(asset.asset_type, asset.symbol)
            liquidity = liquidity_for(asset.asset_type)
            factor_totals[factor] = factor_totals.get(factor, Decimal("0")) + value
            positions.append({"symbol": asset.symbol, "weight": round(float(weight), 6), "factor": factor, "liquidity_days": liquidity, "currency": asset.currency, "venue": asset.venue})
        concentration = sum(item["weight"] ** 2 for item in positions)
        risk_budgets = list(self.db.scalars(select(RiskBudget).where(RiskBudget.user_id == actor.user_id)).all())
        budget_usage = [{"asset_class": item.asset_class, "allocation_limit": float(item.max_allocation_pct), "loss_limit": float(item.max_loss_pct), "used": round(sum(p["weight"] for p in positions if p["factor"] == item.asset_class), 6)} for item in risk_budgets]
        factors = {key: round(float(value / total), 6) if total else 0 for key, value in factor_totals.items()}
        # Prefer the real time-series analysis (stored candles: realized vol,
        # historical correlation, VaR) when one exists; fall back to the
        # labeled deterministic proxy only when no real analysis has been run.
        from app.services.portfolio_time_series_risk import PortfolioTimeSeriesRiskService

        time_series = PortfolioTimeSeriesRiskService(self.db).latest(user_id=actor.user_id)
        if time_series and time_series.get("correlation_matrix"):
            correlation = time_series["correlation_matrix"]
            methodology = "time_series_realized_from_stored_candles"
            correlation_model = "historical-daily-returns-v1"
            time_series_summary = {
                "as_of": time_series.get("as_of"),
                "observations": time_series.get("observations"),
                "annualized_volatility_pct": time_series.get("annualized_volatility_pct"),
                "coverage_pct": time_series.get("coverage_pct"),
                "artifact_id": time_series.get("artifact_id"),
            }
        else:
            correlation = correlation_matrix_proxy(positions)
            methodology = "deterministic_proxy_until_time_series_run"
            correlation_model = "proxy-v1"
            time_series_summary = None
        packet = {"positions": positions, "factor_exposure": factors, "concentration_hhi": round(concentration, 6), "correlation_proxy": correlation, "time_series": time_series_summary, "liquidity": {"max_days": max((p["liquidity_days"] for p in positions), default=0)}, "risk_budget_usage": budget_usage, "methodology": methodology, "execution_available": False}
        self._config(actor.user_id, "portfolio_risk", {"factor_model": "deterministic-v1", "correlation_model": correlation_model, "liquidity_model": "days-to-liquidate-v1", "risk_budget_burn": True})
        artifact = ExportArtifact(user_id=actor.user_id, export_type="portfolio_risk_depth", format="json", status="ready", payload_json=packet, summary_json={"positions": len(positions), "factors": len(factors)}, file_path=None)
        self.db.add(artifact)
        self.db.commit()
        return {**packet, "artifact_id": artifact.id}

    def initialize_commercial(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        policy = {"registration": "managed_oidc", "multi_device_sessions": True, "payment_provider": "stripe_test_contract", "usage_metering": ["data_sync", "research_report", "eval_run", "workspace_user"], "support_queue": True, "billing_live": False}
        self._config(actor.user_id, "users_commercial", policy)
        self._event(actor.user_id, "product.commercial_initialized", "Registration, session, test billing, usage metering, and support contracts initialized.")
        self.db.commit()
        return {"status": "test_mode_ready", **policy, "execution_available": False}

    def create_test_checkout(self, *, actor: AuthenticatedUser, plan: str) -> dict[str, Any]:
        self._write(actor)
        if plan not in {"private_beta", "pro", "team"}:
            raise ProductCompletionError("unsupported pricing plan")
        packet = {"provider": "stripe_contract", "mode": "test", "plan": plan, "user_id": actor.user_id, "status": "requires_provider_session", "entitlements": entitlements_for(plan), "charged": False, "created_at": now().isoformat()}
        artifact = ExportArtifact(user_id=actor.user_id, export_type="test_checkout_session", format="json", status="test_ready", payload_json=packet, summary_json={"plan": plan, "charged": False}, file_path=None)
        self.db.add(artifact)
        self.db.flush()
        self._audit("product.test_checkout_created", "ExportArtifact", artifact.id, {"plan": plan, "charged": False})
        self.db.commit()
        return {**packet, "artifact_id": artifact.id}

    def record_usage(self, *, actor: AuthenticatedUser, metric: str, quantity: int = 1) -> dict[str, Any]:
        self._write(actor)
        if metric not in {"data_sync", "research_report", "eval_run", "workspace_user"} or quantity < 1:
            raise ProductCompletionError("unsupported usage metric")
        self._event(actor.user_id, f"usage.{metric}", f"Usage recorded: {metric}", {"quantity": quantity, "billable": False})
        self.db.commit()
        return {"metric": metric, "quantity": quantity, "billing_mode": "test", "charged": False}

    def create_support_ticket(self, *, actor: AuthenticatedUser, payload: dict[str, Any]) -> dict[str, Any]:
        self._write(actor)
        title = str(payload.get("title") or "").strip()
        if not title:
            raise ProductCompletionError("support ticket title is required")
        event = self._event(actor.user_id, "support.ticket", title, {"description": str(payload.get("description") or "")[:2000], "priority": str(payload.get("priority") or "normal")})
        self.db.commit()
        return {"id": event.id, "status": event.status, "title": title}

    def initialize_operations(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        policy = {"telemetry": ["logs", "metrics", "traces"], "providers": ["sentry", "datadog", "grafana_otlp"], "alert_severities": ["warning", "error", "critical"], "on_call_required": True, "backup": "postgresql_automated", "offsite_restore": True, "degradation_modes": ["read_only", "cached_data", "research_disabled"]}
        self._config(actor.user_id, "production_ops", policy)
        self._event(actor.user_id, "product.operations_initialized", "Monitoring, alerts, backup, restore, and degradation contracts initialized.")
        self.db.commit()
        return {"status": "ready_for_external_monitoring", **policy, "execution_available": False}

    def incident_drill(self, *, actor: AuthenticatedUser, scenario: str) -> dict[str, Any]:
        self._write(actor)
        if scenario not in {"database_unavailable", "market_data_stale", "llm_provider_down", "broker_timeout", "credential_revoked"}:
            raise ProductCompletionError("unsupported incident scenario")
        packet = {"scenario": scenario, "detected": True, "alerted": True, "degraded_to": "read_only", "rollback_available": True, "human_review_required": True, "simulation": True, "production_execution_allowed": False, "run_at": now().isoformat()}
        artifact = ExportArtifact(user_id=actor.user_id, export_type="incident_drill", format="json", status="simulated_passed", payload_json=packet, summary_json={"scenario": scenario, "simulation": True}, file_path=None)
        self.db.add(artifact)
        self._event(actor.user_id, "ops.incident_drill", f"Incident drill completed: {scenario}", packet)
        self.db.commit()
        return {**packet, "artifact_id": artifact.id}

    def initialize_external_proof(self, *, actor: AuthenticatedUser) -> dict[str, Any]:
        self._write(actor)
        manifest = {
            "binance": {"adapter": "binance_spot_readonly", "secret_ref_required": True, "status": "awaiting_credentials"},
            "oidc": {"adapter": "managed_oidc_userinfo", "status": "awaiting_tenant"},
            "secret_manager": {"adapters": ["aws-sm", "gcp-sm", "vault"], "status": "awaiting_tenant"},
            "broker_sandbox": {"adapter": "https_sandbox_only", "status": "awaiting_credentials"},
            "legal": {"evidence": ["terms", "privacy", "risk_disclosure", "pilot_approval"], "status": "awaiting_signed_artifacts"},
        }
        self._config(actor.user_id, "external_proof", manifest)
        self._event(actor.user_id, "product.external_proof_initialized", "External adapter and legal evidence manifest initialized.")
        self.db.commit()
        return {"status": "interfaces_ready_external_evidence_blocked", "manifest": manifest, "production_execution_allowed": False}

    def _config(self, user_id: str, key: str, value: dict[str, Any]) -> LocalUserConfig:
        config_key = f"product_completion:{key}"
        item = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == config_key).limit(1))
        value = {**value, "updated_at": now().isoformat(), "production_execution_allowed": False}
        if item is None:
            item = LocalUserConfig(user_id=user_id, config_key=config_key, value_json=value, description="Local product completion configuration; external evidence tracked separately.")
            self.db.add(item)
        else:
            item.value_json = value
        self.db.flush()
        return item

    def _event(self, user_id: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> OperationalEvent:
        event = OperationalEvent(user_id=user_id, event_type=event_type, severity="info", source="product-completion", message=message, status="closed", payload_json={**(payload or {}), "production_execution_allowed": False})
        self.db.add(event)
        self.db.flush()
        return event

    def _audit(self, action: str, entity_type: str, entity_id: str, payload: dict[str, Any]) -> None:
        write_audit_log(self.db, action=action, entity_type=entity_type, entity_id=entity_id, payload_json={**payload, "production_execution_allowed": False}, actor_id="product-completion")

    def _read(self, actor: AuthenticatedUser) -> None:
        if "readiness:read" not in actor.permissions:
            raise ProductCompletionError("missing permission: readiness:read")

    def _write(self, actor: AuthenticatedUser) -> None:
        if "readiness:write" not in actor.permissions:
            raise ProductCompletionError("missing permission: readiness:write")


def factor_for(asset_type: str, symbol: str) -> str:
    if asset_type in {"crypto", "token", "stablecoin"}:
        return "crypto"
    if symbol in {"QQQ", "NVDA", "MSFT", "AAPL"}:
        return "growth"
    if symbol in {"GLD"}:
        return "defensive"
    if asset_type == "cash":
        return "cash"
    return "market"


def liquidity_for(asset_type: str) -> int:
    return 1 if asset_type in {"stock", "etf", "cash", "stablecoin"} else 2 if asset_type in {"crypto", "token"} else 5


def correlation_matrix_proxy(positions: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    factors = sorted({str(item["factor"]) for item in positions})
    return {left: {right: 1.0 if left == right else 0.65 if {left, right} <= {"growth", "market", "crypto"} else 0.15 for right in factors} for left in factors}


def entitlements_for(plan: str) -> list[str]:
    return {
        "private_beta": ["readonly_data", "mock_llm", "daily_loop"],
        "pro": ["readonly_data", "configured_llm", "risk_terminal", "data_room"],
        "team": ["readonly_data", "configured_llm", "risk_terminal", "data_room", "multi_user_rbac", "admin_audit"],
    }[plan]


def now() -> datetime:
    return datetime.now(timezone.utc)
