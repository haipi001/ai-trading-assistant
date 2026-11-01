from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.core.config import get_settings
from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import InvestmentThesis
from app.models import LocalUserConfig
from app.models import OperationalEvent
from app.models import OrderDraft
from app.models import Position
from app.models import ResearchReport
from app.models import SecretReference
from app.models import StatementImportBatch
from app.models import UserAccount
from app.schemas.core import contains_secret_config_key
from app.schemas.core import looks_like_inline_secret_reference
from app.services.daily_use import DailyUseService
from app.services.data_sources import DataSourceError
from app.services.data_sources import DataSourceService
from app.services.ledger import InvestmentLedgerService
from app.services.product_roadmap import ProductRoadmapService


class PhaseDevelopmentService:
    def __init__(self, db: Session):
        self.db = db

    def summary(self, *, user_id: str = "default-user") -> dict[str, Any]:
        phases = [
            self.founder_daily_use_alpha(user_id=user_id),
            self.real_readonly_data_proof(user_id=user_id),
            self.trusted_ledger(user_id=user_id),
            self.research_evidence(user_id=user_id),
            self.portfolio_risk_terminal(user_id=user_id),
            self.private_beta_foundation(user_id=user_id),
            self.traction_loop(user_id=user_id),
            self.broker_sandbox_proof(user_id=user_id),
            self.controlled_pilot(user_id=user_id),
        ]
        return {
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc),
            "status": "development_safe_slices",
            "phases_total": len(phases),
            "developed_safe_slices": len(phases),
            "average_progress_pct": round(sum(item["progress_pct"] for item in phases) / len(phases)),
            "current_phase": phases[0],
            "next_phase": phases[1],
            "phases": phases,
            "next_actions": [action for phase in phases[:3] for action in phase["next_actions"][:1]],
            "execution_available": False,
            "production_capability": False,
        }

    def phase(self, *, phase_key: str, user_id: str = "default-user") -> dict[str, Any]:
        phase_map = {
            "founder_daily_use_alpha": self.founder_daily_use_alpha,
            "real_readonly_data_proof": self.real_readonly_data_proof,
            "trusted_ledger": self.trusted_ledger,
            "trusted_ledger_data_promotion": self.trusted_ledger,
            "research_evidence": self.research_evidence,
            "research_evidence_thesis_delta": self.research_evidence,
            "portfolio_risk_terminal": self.portfolio_risk_terminal,
            "private_beta_foundation": self.private_beta_foundation,
            "traction_loop": self.traction_loop,
            "traction_commercial_loop": self.traction_loop,
            "broker_sandbox_proof": self.broker_sandbox_proof,
            "broker_sandbox_execution_proof": self.broker_sandbox_proof,
            "controlled_pilot": self.controlled_pilot,
        }
        if phase_key not in phase_map:
            raise ValueError("phase development key not found")
        return phase_map[phase_key](user_id=user_id)

    def founder_daily_use_alpha(self, *, user_id: str = "default-user") -> dict[str, Any]:
        daily = DailyUseService(self.db)
        onboarding = daily.onboarding_status(user_id=user_id)
        queue = daily.action_queue(user_id=user_id, limit=10)
        overview = daily.overview(user_id=user_id)
        progress = 70
        if onboarding["status"] != "ready":
            progress -= 15
        if queue["total_actions"] == 0:
            progress -= 10
        return phase_packet(
            1,
            "founder_daily_use_alpha",
            "Founder Daily-Use Alpha",
            "usable_alpha" if progress >= 65 else "needs_onboarding",
            max(progress, 45),
            {
                "onboarding": onboarding,
                "today_queue": queue,
                "overview": overview,
                "daily_open_endpoint": "/daily-use/daily-open",
                "daily_close_endpoint": "/daily-use/daily-close",
                "drilldown_endpoint": "/daily-use/drilldown/{queue_item_id}",
            },
            [
                "Complete founder onboarding and set a daily review cadence.",
                "Use today action queue as the default first screen.",
                "Open the highest-priority queue drilldown before creating new work.",
            ],
        )

    def real_readonly_data_proof(self, *, user_id: str = "default-user") -> dict[str, Any]:
        connection = self.db.scalar(
            select(DataSourceConnection)
            .where(DataSourceConnection.provider == "binance_spot_readonly")
            .order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
            .limit(1)
        )
        snapshots = list(
            self.db.scalars(
                select(DataSnapshot)
                .where(DataSnapshot.snapshot_type == "read_only_account")
                .order_by(DataSnapshot.created_at.desc(), DataSnapshot.id.desc())
                .limit(20)
            ).all()
        )
        snapshot = next(
            (
                item
                for item in snapshots
                if item.metadata_json.get("provider") == "binance_spot_readonly"
                or item.data_json.get("provider") == "binance_spot_readonly"
            ),
            None,
        )
        quality_report = None
        if snapshot is not None:
            quality_report = self.db.scalar(
                select(DataQualityReport)
                .where(DataQualityReport.data_snapshot_id == snapshot.id)
                .order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())
                .limit(1)
            )
        evidence_ready = bool(connection and connection.credentials_ref and snapshot)
        return phase_packet(
            2,
            "real_readonly_data_proof",
            "Real Read-Only Data Proof",
            "evidence_ready" if evidence_ready else "needs_private_verification",
            60 if evidence_ready else 45 if connection else 35,
            {
                "provider": "binance_spot_readonly",
                "connection_configured": connection is not None,
                "connection_status": connection.status if connection else None,
                "has_credentials_ref": bool(connection and connection.credentials_ref),
                "latest_snapshot_id": snapshot.id if snapshot else None,
                "latest_snapshot_as_of": snapshot.as_of if snapshot else None,
                "quality_report_id": quality_report.id if quality_report else None,
                "quality_score": float(quality_report.score) if quality_report else None,
                "private_verification_required": True,
                "forbidden": ["order_placement", "withdrawal", "wallet_signing", "production_trading"],
            },
            [
                "Run binance_spot_readonly with a real read-only key in a private environment.",
                "Save the account snapshot, quality report, and audit evidence packet.",
                "Keep credentials referenced only; never store key material inline.",
            ],
        )

    def verify_binance_readonly_private(
        self,
        *,
        user_id: str = "default-user",
        evidence_refs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        evidence_refs = dict(evidence_refs or {})
        if contains_secret_config_key(evidence_refs):
            raise ValueError("private verification evidence must contain references only, never credentials")
        if any(
            key.endswith("_ref") and isinstance(value, str) and looks_like_inline_secret_reference(value)
            for key, value in evidence_refs.items()
        ):
            raise ValueError("private verification evidence refs must not contain inline credentials")
        allowed_evidence_keys = {
            "permission_screenshot_ref",
            "withdrawal_disabled_proof_ref",
            "operator_note",
            "verification_environment",
        }
        unknown_keys = sorted(set(evidence_refs) - allowed_evidence_keys)
        if unknown_keys:
            raise ValueError(f"unsupported private verification evidence field(s): {', '.join(unknown_keys)}")
        connection = self.db.scalar(
            select(DataSourceConnection)
            .where(DataSourceConnection.provider == "binance_spot_readonly")
            .order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
            .limit(1)
        )
        if connection is None:
            return {
                "user_id": user_id,
                "generated_at": generated_at,
                "status": "missing_connection",
                "provider": "binance_spot_readonly",
                "evidence_packet": self.real_readonly_data_proof(user_id=user_id)["evidence_packet"],
                "blockers": ["binance_spot_readonly_connection_missing"],
                "evidence_refs": evidence_refs,
                "next_actions": ["Create a binance_spot_readonly data source connection with a credentials_ref."],
                "execution_available": False,
                "production_capability": False,
            }
        service = DataSourceService(self.db)
        preflight = service.read_only_preflight(connection.id)
        certification = service.read_only_certification(connection.id)
        sync_result: dict[str, Any] | None = None
        sync_error: str | None = None
        proof_blockers: list[str] = []
        if not evidence_refs.get("permission_screenshot_ref"):
            proof_blockers.append("permission_screenshot_ref_required")
        if not evidence_refs.get("withdrawal_disabled_proof_ref"):
            proof_blockers.append("withdrawal_disabled_proof_ref_required")
        verification_environment = str(evidence_refs.get("verification_environment") or "").strip().lower()
        if verification_environment not in {"private", "private_local", "private_ci"}:
            proof_blockers.append("private_verification_environment_required")

        ledger_sync: dict[str, Any] | None = None
        reconciliation: dict[str, Any] | None = None
        if preflight.status != "blocked" and bool(connection.credentials_ref) and not proof_blockers:
            try:
                result = service.sync_account_snapshot(connection.id, user_id=user_id, trigger="private_verification")
                ledger_sync = result.ledger_sync
                reconciliation = result.reconciliation
                sync_result = {
                    "account_id": result.account.id,
                    "snapshot_id": result.snapshot.id,
                    "quality_report_id": result.quality_report.id,
                    "quality_score": float(result.quality_report.score),
                    "catalog_entry_id": result.catalog_entry.id,
                    "positions_synced": result.positions_synced,
                    "balances_synced": result.balances_synced,
                    "orders_seen": result.orders_seen,
                }
            except DataSourceError as exc:
                sync_error = str(exc)
        verification_checks_passed = bool(
            sync_result
            and sync_result.get("snapshot_id")
            and sync_result.get("quality_report_id")
            and sync_result.get("catalog_entry_id")
            and float(sync_result.get("quality_score") or 0) >= 0.8
            and ledger_sync is not None
            and reconciliation is not None
            and reconciliation.get("status") == "ok"
            and not proof_blockers
        )
        status = "verified_private_readonly" if verification_checks_passed else "verification_blocked"
        packet = {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": status,
            "provider": "binance_spot_readonly",
            "connection_id": connection.id,
            "has_credentials_ref": bool(connection.credentials_ref),
            "preflight_status": preflight.status,
            "certification_status": certification.status,
            "sync_result": sync_result,
            "sync_error": sync_error,
            "proof_blockers": proof_blockers,
            "ledger_sync": ledger_sync,
            "reconciliation": reconciliation,
            "evidence_refs": evidence_refs,
            "proof_checks": {
                "permission_screenshot_recorded": bool(evidence_refs.get("permission_screenshot_ref")),
                "withdrawal_disabled_proof_recorded": bool(evidence_refs.get("withdrawal_disabled_proof_ref")),
                "snapshot_recorded": bool(sync_result and sync_result.get("snapshot_id")),
                "quality_report_recorded": bool(sync_result and sync_result.get("quality_report_id")),
                "quality_report_passed": bool(sync_result and float(sync_result.get("quality_score") or 0) >= 0.8),
                "catalog_lineage_recorded": bool(sync_result and sync_result.get("catalog_entry_id")),
                "ledger_sync_recorded": ledger_sync is not None,
                "reconciliation_passed": bool(reconciliation and reconciliation.get("status") == "ok"),
            },
            "forbidden": ["order_placement", "withdrawal", "wallet_signing", "production_trading"],
            "execution_available": False,
            "production_capability": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="binance_readonly_private_evidence",
            format="json",
            status="ready" if sync_result else "blocked",
            payload_json=jsonable_encoder(packet),
            summary_json={
                "provider": "binance_spot_readonly",
                "status": status,
                "contains_credentials": False,
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["audit_packet_artifact_id"] = artifact.id
        self._audit(
            "phase_development.binance_readonly_private_verified",
            "DataSourceConnection",
            connection.id,
            jsonable_encoder(packet),
        )
        self.db.commit()
        return packet

    def trusted_ledger(self, *, user_id: str = "default-user") -> dict[str, Any]:
        ledger = InvestmentLedgerService(self.db)
        promotion = ledger.data_promotion_report(user_id=user_id)
        workbench = ledger.reconciliation_workbench(user_id=user_id)
        status = "trusted" if promotion["can_promote_to_trusted"] else "review_required"
        return phase_packet(
            3,
            "trusted_ledger",
            "Trusted Ledger",
            status,
            60 if status == "trusted" else 45,
            {
                "normalization": promotion["normalization"],
                "promotion": promotion,
                "reconciliation_workbench": workbench,
                "repair_workflow_endpoint": "/ledger/repair-workflow",
            },
            promotion["next_actions"][:4],
        )

    def verify_ibkr_readonly_private(
        self,
        *,
        user_id: str = "default-user",
        evidence_refs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        evidence_refs = dict(evidence_refs or {})
        if contains_secret_config_key(evidence_refs):
            raise ValueError("private verification evidence must contain references only, never credentials")
        if any(
            key.endswith("_ref") and isinstance(value, str) and looks_like_inline_secret_reference(value)
            for key, value in evidence_refs.items()
        ):
            raise ValueError("private verification evidence refs must not contain inline credentials")
        allowed_keys = {
            "gateway_session_proof_ref",
            "read_only_boundary_proof_ref",
            "operator_note",
            "verification_environment",
        }
        unknown_keys = sorted(set(evidence_refs) - allowed_keys)
        if unknown_keys:
            raise ValueError(f"unsupported private verification evidence field(s): {', '.join(unknown_keys)}")
        connection = self.db.scalar(
            select(DataSourceConnection)
            .where(DataSourceConnection.provider == "ibkr_readonly")
            .order_by(DataSourceConnection.created_at.desc(), DataSourceConnection.id.desc())
            .limit(1)
        )
        if connection is None:
            return {
                "user_id": user_id,
                "generated_at": generated_at,
                "status": "missing_connection",
                "provider": "ibkr_readonly",
                "blockers": ["ibkr_readonly_connection_missing"],
                "evidence_refs": evidence_refs,
                "execution_available": False,
                "production_capability": False,
            }
        proof_blockers: list[str] = []
        if not evidence_refs.get("gateway_session_proof_ref"):
            proof_blockers.append("gateway_session_proof_ref_required")
        if not evidence_refs.get("read_only_boundary_proof_ref"):
            proof_blockers.append("read_only_boundary_proof_ref_required")
        verification_environment = str(evidence_refs.get("verification_environment") or "").strip().lower()
        if verification_environment not in {"private", "private_local", "private_ci"}:
            proof_blockers.append("private_verification_environment_required")

        service = DataSourceService(self.db)
        preflight = service.read_only_preflight(connection.id)
        certification = service.read_only_certification(connection.id)
        sync_result: dict[str, Any] | None = None
        sync_error: str | None = None
        if preflight.status != "blocked" and connection.credentials_ref and not proof_blockers:
            try:
                result = service.sync_account_snapshot(connection.id, user_id=user_id, trigger="private_verification")
                sync_result = {
                    "account_id": result.account.id if result.account else None,
                    "snapshot_id": result.snapshot.id,
                    "quality_report_id": result.quality_report.id,
                    "quality_score": float(result.quality_report.score),
                    "catalog_entry_id": result.catalog_entry.id,
                    "positions_synced": result.positions_synced,
                    "balances_synced": result.balances_synced,
                    "orders_seen": result.orders_seen,
                    "ledger_sync": result.ledger_sync,
                    "reconciliation": result.reconciliation,
                }
            except DataSourceError as exc:
                sync_error = str(exc)
        checks = {
            "gateway_session_proof_recorded": bool(evidence_refs.get("gateway_session_proof_ref")),
            "read_only_boundary_proof_recorded": bool(evidence_refs.get("read_only_boundary_proof_ref")),
            "snapshot_recorded": bool(sync_result and sync_result.get("snapshot_id")),
            "quality_report_passed": bool(sync_result and float(sync_result.get("quality_score") or 0) >= 0.8),
            "catalog_lineage_recorded": bool(sync_result and sync_result.get("catalog_entry_id")),
            "ledger_sync_recorded": bool(sync_result and sync_result.get("ledger_sync")),
            "reconciliation_passed": bool(
                sync_result
                and (sync_result.get("reconciliation") or {}).get("status") == "ok"
            ),
            "orders_endpoint_not_used": bool(sync_result and sync_result.get("orders_seen") == 0),
        }
        verified = bool(all(checks.values()) and not proof_blockers and sync_error is None)
        status = "verified_private_readonly" if verified else "verification_blocked"
        packet = {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": status,
            "provider": "ibkr_readonly",
            "connection_id": connection.id,
            "preflight_status": preflight.status,
            "certification_status": certification.status,
            "sync_result": sync_result,
            "sync_error": sync_error,
            "proof_blockers": proof_blockers,
            "evidence_refs": evidence_refs,
            "proof_checks": checks,
            "read_endpoints": ["/portfolio/accounts", "/portfolio/{accountId}/positions/{pageId}", "/portfolio/{accountId}/ledger"],
            "forbidden": ["order_endpoint", "order_placement", "withdrawal", "production_trading"],
            "execution_available": False,
            "production_capability": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="ibkr_readonly_private_evidence",
            format="json",
            status="ready" if verified else "blocked",
            payload_json=jsonable_encoder(packet),
            summary_json={
                "provider": "ibkr_readonly",
                "status": status,
                "contains_credentials": False,
                "execution_available": False,
            },
            file_path=None,
        )
        self.db.add(artifact)
        self.db.flush()
        packet["audit_packet_artifact_id"] = artifact.id
        self._audit(
            "phase_development.ibkr_readonly_private_verified",
            "DataSourceConnection",
            connection.id,
            jsonable_encoder(packet),
        )
        self.db.commit()
        return packet

    def research_evidence(self, *, user_id: str = "default-user") -> dict[str, Any]:
        settings = get_settings()
        research_config = self._phase_config(user_id=user_id, key="research_evidence_config")
        reports_count = self._count(select(func.count()).select_from(ResearchReport))
        active_theses = self._count(
            select(func.count()).select_from(InvestmentThesis).where(InvestmentThesis.user_id == user_id, InvestmentThesis.status == "active")
        )
        latest_report = self.db.scalar(select(ResearchReport).order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc()).limit(1))
        configured_secret_ref = research_config.get("credential_reference") or research_config.get("secret_reference")
        llm_allowlist = research_config.get("llm_allowlist") or research_config.get("allowlist") or []
        llm_ready = settings.external_llm_calls_enabled and (bool(settings.openai_api_key_ref) or bool(configured_secret_ref))
        eval_status = "ready_for_eval" if latest_report and latest_report.evidence else "needs_evidence_packet"
        return phase_packet(
            4,
            "research_evidence",
            "Research Evidence",
            "safe_llm_ready" if llm_ready else eval_status,
            55 if latest_report else 35,
            {
                "external_llm_calls_enabled": settings.external_llm_calls_enabled,
                "openai_api_key_ref_configured": bool(settings.openai_api_key_ref),
                "configured_llm_allowlist": llm_allowlist,
                "configured_secret_reference": configured_secret_ref,
                "structured_eval_config": research_config.get("structured_eval", {}),
                "reports_count": reports_count,
                "active_theses_count": active_theses,
                "latest_report": research_report_payload(latest_report),
                "thesis_delta": thesis_delta_payload(latest_report, active_theses),
                "eval": {
                    "status": eval_status,
                    "requires_structured_output": True,
                    "requires_snapshot_citations": True,
                    "execution_available": False,
                },
            },
            [
                "Enable real LLM calls only with an allowlisted provider and referenced secret.",
                "Attach every research report to source snapshots and evidence.",
                "Compare new findings against active thesis checkpoints before changing priority.",
            ],
        )

    def configure_research_evidence(self, *, user_id: str = "default-user", payload: dict[str, Any]) -> dict[str, Any]:
        self._store_phase_config(user_id=user_id, key="research_evidence_config", payload=payload)
        return self.research_evidence(user_id=user_id)

    def research_eval_packet(self, *, user_id: str = "default-user") -> dict[str, Any]:
        phase = self.research_evidence(user_id=user_id)
        evidence = phase["evidence_packet"]
        latest_report = evidence.get("latest_report")
        checks = [
            phase_check("llm_secret_reference", bool(evidence.get("openai_api_key_ref_configured")), "LLM key must be referenced, never stored inline."),
            phase_check("snapshot_citations", bool(latest_report and latest_report.get("data_snapshot_id")), "Latest report must cite a data snapshot."),
            phase_check("structured_evidence", bool(latest_report and latest_report.get("has_evidence")), "Latest report must carry structured evidence."),
            phase_check("thesis_delta", evidence["thesis_delta"]["status"] != "missing_report", "Thesis delta must be reviewed before changing priority."),
        ]
        packet = {
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc),
            "status": "ready_for_human_eval" if all(item["passed"] for item in checks) else "blocked",
            "checks": checks,
            "evidence_packet": evidence,
            "execution_available": False,
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="research_structured_eval",
            format="json",
            status=packet["status"],
            payload_json=jsonable_encoder(packet),
            summary_json={"checks_passed": sum(1 for item in checks if item["passed"]), "checks_total": len(checks)},
            file_path=None,
        )
        self.db.add(artifact)
        self.db.commit()
        packet["eval_artifact_id"] = artifact.id
        return packet

    def research_eval_history(self, *, user_id: str = "default-user") -> dict[str, Any]:
        artifacts = list(
            self.db.scalars(
                select(ExportArtifact)
                .where(ExportArtifact.user_id == user_id, ExportArtifact.export_type == "research_structured_eval")
                .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
                .limit(50)
            ).all()
        )
        return {
            "user_id": user_id,
            "generated_at": datetime.now(timezone.utc),
            "total": len(artifacts),
            "items": [
                {
                    "id": item.id,
                    "status": item.status,
                    "created_at": item.created_at,
                    "summary": item.summary_json,
                    "thesis_delta": item.payload_json.get("evidence_packet", {}).get("thesis_delta"),
                }
                for item in artifacts
            ],
            "execution_available": False,
        }

    def portfolio_risk_terminal(self, *, user_id: str = "default-user") -> dict[str, Any]:
        positions = list(self.db.scalars(select(Position).order_by(Position.updated_at.desc(), Position.id.desc()).limit(500)).all())
        total_value = sum(float(item.market_value or 0) for item in positions)
        asset_ids = {item.asset_id for item in positions}
        assets = {asset.id: asset for asset in self.db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()} if asset_ids else {}
        exposures: dict[str, float] = {}
        exposure_by_account: dict[str, float] = {}
        exposure_by_currency: dict[str, float] = {}
        exposure_by_venue: dict[str, float] = {}
        exposure_by_factor: dict[str, float] = {}
        drilldowns: list[dict[str, Any]] = []
        for item in positions:
            asset = assets.get(item.asset_id)
            asset_type = asset.asset_type if asset else "unknown"
            currency = asset.currency if asset else "UNKNOWN"
            venue = asset.venue or asset.exchange or "unknown" if asset else "unknown"
            factor = asset.risk_level if asset else "unknown"
            value = float(item.market_value or 0)
            exposures[asset_type] = exposures.get(asset_type, 0.0) + value
            exposure_by_account[item.account_id] = exposure_by_account.get(item.account_id, 0.0) + value
            exposure_by_currency[currency] = exposure_by_currency.get(currency, 0.0) + value
            exposure_by_venue[venue] = exposure_by_venue.get(venue, 0.0) + value
            exposure_by_factor[factor] = exposure_by_factor.get(factor, 0.0) + value
            drilldowns.append(
                {
                    "position_id": item.id,
                    "asset_id": item.asset_id,
                    "symbol": asset.symbol if asset else item.asset_id,
                    "asset_type": asset_type,
                    "account_id": item.account_id,
                    "currency": currency,
                    "venue": venue,
                    "factor": factor,
                    "market_value": value,
                    "weight": float(item.weight or 0),
                    "risk_flag": "concentrated" if total_value and value / total_value > 0.25 else "normal",
                }
            )
        drilldowns.sort(key=lambda item: item["market_value"], reverse=True)
        stress = [
            {"scenario": "market_down_10pct", "estimated_pnl": round(total_value * -0.10, 2)},
            {"scenario": "market_down_25pct", "estimated_pnl": round(total_value * -0.25, 2)},
            {"scenario": "single_largest_position_down_30pct", "estimated_pnl": round((drilldowns[0]["market_value"] if drilldowns else 0) * -0.30, 2)},
        ]
        return phase_packet(
            5,
            "portfolio_risk_terminal",
            "Portfolio Risk Terminal",
            "risk_terminal_ready" if positions else "needs_holdings",
            55 if positions else 35,
            {
                "positions_count": len(positions),
                "total_market_value": round(total_value, 2),
                "exposure_by_asset_type": exposures,
                "exposure_by_account": exposure_by_account,
                "exposure_by_currency": exposure_by_currency,
                "exposure_by_venue": exposure_by_venue,
                "exposure_by_factor": exposure_by_factor,
                "concentration": drilldowns[:10],
                "stress_scenarios": stress,
            },
            [
                "Review concentrated exposures and stale holdings before adding any execution surface.",
                "Link high-risk positions back to thesis and ledger evidence.",
                "Add account, currency, venue, and factor drilldowns as portfolio data grows.",
            ],
        )

    def portfolio_risk_drilldown(self, *, dimension: str, user_id: str = "default-user") -> dict[str, Any]:
        if dimension not in {"account", "currency", "venue", "factor"}:
            raise ValueError("unsupported risk drilldown dimension")
        packet = self.portfolio_risk_terminal(user_id=user_id)["evidence_packet"]
        key = f"exposure_by_{dimension}"
        return {
            "user_id": user_id,
            "dimension": dimension,
            "generated_at": datetime.now(timezone.utc),
            "status": "ready",
            "exposure": packet.get(key, {}),
            "concentration": packet.get("concentration", []),
            "stress_scenarios": packet.get("stress_scenarios", []),
            "today_queue_source": "portfolio_risk",
            "deep_links": {
                "positions": "/?module=holdings",
                "theses": "/?module=investment_logic",
                "ledger": "/?module=trade_journal&tab=ledger",
                "today_queue": "/?module=overview&focus=today_queue",
            },
            "execution_available": False,
        }

    def private_beta_foundation(self, *, user_id: str = "default-user") -> dict[str, Any]:
        settings = get_settings()
        checklist = self._phase_config(user_id=user_id, key="private_beta_foundation_checklist")
        users = self._count(select(func.count()).select_from(UserAccount))
        secrets = self._count(select(func.count()).select_from(SecretReference).where(SecretReference.user_id == user_id))
        events = self._count(select(func.count()).select_from(OperationalEvent))
        backups = self._count(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.user_id == user_id, ExportArtifact.export_type == "local_backup_manifest"))
        auth_ready = settings.beta_auth_required and users > 0
        checklist_ready = all(
            bool(checklist.get(key))
            for key in ["auth", "rbac", "secrets", "monitoring", "backups", "admin_console"]
        )
        return phase_packet(
            6,
            "private_beta_foundation",
            "Private Beta Foundation",
            "beta_foundation_ready" if auth_ready and backups and checklist_ready else "foundation_incomplete",
            65 if checklist_ready else 55 if auth_ready else 40,
            {
                "auth_required": settings.beta_auth_required,
                "users_count": users,
                "secret_references_count": secrets,
                "operational_events_count": events,
                "backup_manifests_count": backups,
                "monitoring_enabled": settings.error_reporting_enabled,
                "admin_surface_required": True,
                "admin_console_checklist": checklist,
            },
            [
                "Require real auth/RBAC outside local development.",
                "Verify secret references, monitoring, restore drills, and backup manifests.",
                "Add admin views for users, events, jobs, and data freshness.",
            ],
        )

    def update_private_beta_foundation(self, *, user_id: str = "default-user", payload: dict[str, Any]) -> dict[str, Any]:
        self._store_phase_config(user_id=user_id, key="private_beta_foundation_checklist", payload=payload)
        event = OperationalEvent(
            user_id=user_id,
            event_type="private_beta_foundation_updated",
            severity="info",
            source="phase_development",
            message="Private beta foundation checklist updated.",
            status="closed",
            payload_json={"keys": sorted(payload.keys()), "execution_available": False},
        )
        self.db.add(event)
        self.db.commit()
        return self.private_beta_foundation(user_id=user_id)

    def traction_loop(self, *, user_id: str = "default-user") -> dict[str, Any]:
        traction_config = self._phase_config(user_id=user_id, key="traction_loop_config")
        waitlist = self._count(select(func.count()).select_from(UserAccount).where(UserAccount.status == "invited"))
        analytics_events = self._count(select(func.count()).select_from(AuditLog))
        data_room_exports = self._count(select(func.count()).select_from(ExportArtifact).where(ExportArtifact.user_id == user_id))
        pricing_config = self.db.scalar(
            select(LocalUserConfig)
            .where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == "pricing_hypothesis")
            .limit(1)
        )
        return phase_packet(
            7,
            "traction_loop",
            "Traction Loop",
            "commercial_loop_started" if analytics_events else "needs_waitlist_analytics",
            45 if analytics_events else 30,
            {
                "waitlist_count": waitlist,
                "analytics_events_count": analytics_events,
                "pricing_hypothesis": pricing_config.value_json if pricing_config else None,
                "loop_config": traction_config,
                "data_room_exports_count": data_room_exports,
                "demo_repeatability": data_room_exports > 0,
            },
            [
                "Add waitlist capture, invite status, and activation analytics.",
                "Record pricing hypothesis and usage limits in local config.",
                "Create repeatable demo and data room exports from safe evidence packets.",
            ],
        )

    def update_traction_loop(self, *, user_id: str = "default-user", payload: dict[str, Any]) -> dict[str, Any]:
        self._store_phase_config(user_id=user_id, key="traction_loop_config", payload=payload)
        if payload.get("data_room_export") is True:
            artifact = ExportArtifact(
                user_id=user_id,
                export_type="data_room",
                format="json",
                status="ready",
                payload_json={
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "sections": ["phase_development", "readiness", "evidence_packets"],
                    "execution_available": False,
                },
                summary_json={"source": "traction_loop", "execution_available": False},
                file_path=None,
            )
            self.db.add(artifact)
            self.db.commit()
        return self.traction_loop(user_id=user_id)

    def broker_sandbox_proof(self, *, user_id: str = "default-user") -> dict[str, Any]:
        settings = get_settings()
        state_config = self._phase_config(user_id=user_id, key="broker_sandbox_state_machine")
        drafts = self._count(select(func.count()).select_from(OrderDraft))
        sandbox_audits = self._count(select(func.count()).select_from(AuditLog).where(AuditLog.action.contains("sandbox")))
        return phase_packet(
            8,
            "broker_sandbox_proof",
            "Broker Sandbox Proof",
            "locked_sandbox_design" if not sandbox_audits else "sandbox_evidence_started",
            30 if sandbox_audits else 20,
            {
                "live_execution_enabled": settings.live_execution_enabled,
                "live_execution_dry_run_only": settings.live_execution_dry_run_only,
                "adapter_mode": settings.live_execution_adapter_mode,
                "order_drafts_count": drafts,
                "sandbox_audit_events_count": sandbox_audits,
                "required_state_machine": ["drafted", "validated", "submitted_sandbox", "accepted", "filled_or_cancelled", "reconciled"],
                "configured_state_machine": state_config,
                "idempotency_key": state_config.get("idempotency_key"),
                "production_execution_allowed": False,
            },
            [
                "Define sandbox adapter contract and idempotent order state machine.",
                "Audit every sandbox state transition and reconcile it back to ledger.",
                "Keep production execution disabled until legal, ops, monitoring, and kill switch gates pass.",
            ],
        )

    def update_broker_sandbox_state(self, *, user_id: str = "default-user", payload: dict[str, Any]) -> dict[str, Any]:
        state_order = ["drafted", "validated", "submitted_sandbox", "accepted", "filled_or_cancelled", "reconciled"]
        allowed_states = set(state_order)
        state = str(payload.get("state") or "drafted")
        if state not in allowed_states:
            raise ValueError("unsupported sandbox order state")
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise ValueError("sandbox transition requires an idempotency_key")
        existing = self._phase_config(user_id=user_id, key="broker_sandbox_state_machine")
        previous_state = str(existing.get("state") or "drafted")
        if existing.get("idempotency_key") == idempotency_key:
            return self.broker_sandbox_proof(user_id=user_id)
        if state_order.index(state) not in {state_order.index(previous_state), state_order.index(previous_state) + 1}:
            raise ValueError(f"invalid sandbox state transition: {previous_state} -> {state}")
        if state == "reconciled" and payload.get("ledger_reconciliation_required") is not True:
            raise ValueError("reconciled state requires ledger_reconciliation_required=true")
        safe_payload = {
            **payload,
            "state": state,
            "previous_state": previous_state,
            "idempotency_key": idempotency_key,
            "adapter_contract": "sandbox_only_no_live_credentials",
            "production_execution_allowed": False,
            "execution_available": False,
        }
        self._store_phase_config(user_id=user_id, key="broker_sandbox_state_machine", payload=safe_payload)
        self._audit("phase_development.broker_sandbox_state_updated", "LocalUserConfig", "broker_sandbox_state_machine", safe_payload)
        return self.broker_sandbox_proof(user_id=user_id)

    def controlled_pilot(self, *, user_id: str = "default-user") -> dict[str, Any]:
        configs = {
            item.config_key: item.value_json
            for item in self.db.scalars(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id)).all()
        }
        gates = {
            "legal_approval": bool(configs.get("pilot_legal_approval", {}).get("approved")),
            "ops_approval": bool(configs.get("pilot_ops_approval", {}).get("approved")),
            "allowlist_ready": bool(configs.get("pilot_allowlist", {}).get("enabled")),
            "hard_limits_ready": bool(configs.get("pilot_limits", {}).get("configured")),
            "monitoring_ready": bool(configs.get("pilot_monitoring", {}).get("enabled")),
            "rollback_ready": bool(configs.get("pilot_rollback", {}).get("ready")),
            "kill_switch_ready": bool(configs.get("pilot_kill_switch", {}).get("enabled")),
        }
        passed = all(gates.values())
        return phase_packet(
            9,
            "controlled_pilot",
            "Controlled Pilot",
            "pilot_locked" if not passed else "pilot_gate_review_required",
            10 if not passed else 45,
            {
                "gates": gates,
                "small_pilot_allowed": False,
                "requires_explicit_human_release": True,
                "forbidden_until_release": ["real_money_order", "broker_production_credentials", "wallet_signing", "withdrawal", "dex_swap", "auto_approval"],
            },
            [
                "Do not start a pilot until legal, ops, allowlist, limits, monitoring, and rollback gates pass.",
                "Define hard stop conditions and pilot scope before any small-money discussion.",
                "Require explicit human approval after phases 1-8 produce passing evidence.",
            ],
        )

    def update_controlled_pilot_gates(self, *, user_id: str = "default-user", payload: dict[str, Any]) -> dict[str, Any]:
        for key in [
            "pilot_legal_approval",
            "pilot_ops_approval",
            "pilot_allowlist",
            "pilot_limits",
            "pilot_monitoring",
            "pilot_rollback",
            "pilot_kill_switch",
        ]:
            if key in payload:
                self._store_phase_config(user_id=user_id, key=key, payload=payload[key])
        self._audit("phase_development.controlled_pilot_gates_updated", "LocalUserConfig", "controlled_pilot", {"keys": sorted(payload.keys()), "execution_available": False})
        return self.controlled_pilot(user_id=user_id)

    def _count(self, query: Any) -> int:
        return int(self.db.scalar(query) or 0)

    def _store_phase_config(self, *, user_id: str, key: str, payload: dict[str, Any]) -> LocalUserConfig:
        validation_payload = dict(payload)
        if key == "private_beta_foundation_checklist" and isinstance(validation_payload.get("secrets"), bool):
            validation_payload.pop("secrets")
        if contains_secret_config_key(validation_payload):
            raise ValueError("phase configuration must not contain inline secrets")
        config = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == key).limit(1))
        value = {**payload, "updated_at": datetime.now(timezone.utc).isoformat(), "execution_available": False}
        if config is None:
            config = LocalUserConfig(user_id=user_id, config_key=key, value_json=value, description="Phase development configuration.")
            self.db.add(config)
        else:
            config.value_json = value
            config.description = "Phase development configuration."
        self.db.flush()
        self._audit("phase_development.config_updated", "LocalUserConfig", key, {"user_id": user_id, "config_key": key, "execution_available": False})
        self.db.commit()
        self.db.refresh(config)
        return config

    def _phase_config(self, *, user_id: str, key: str) -> dict[str, Any]:
        config = self.db.scalar(select(LocalUserConfig).where(LocalUserConfig.user_id == user_id, LocalUserConfig.config_key == key).limit(1))
        return dict(config.value_json) if config and isinstance(config.value_json, dict) else {}

    def _audit(self, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        write_audit_log(
            self.db,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=payload_json,
            actor_id="phase-development-service",
        )


def phase_packet(
    phase_no: int,
    key: str,
    title: str,
    status: str,
    progress_pct: int,
    evidence_packet: dict[str, Any],
    next_actions: list[str],
) -> dict[str, Any]:
    roadmap_key = {
        "trusted_ledger": "trusted_ledger_data_promotion",
        "research_evidence": "research_evidence_thesis_delta",
        "traction_loop": "traction_commercial_loop",
        "broker_sandbox_proof": "broker_sandbox_execution_proof",
    }.get(key, key)
    roadmap_phase = next(
        (item for item in ProductRoadmapService().phases() if item["key"] == roadmap_key or item["title"] == title),
        None,
    )
    return {
        "phase_no": phase_no,
        "key": key,
        "title": title,
        "status": status,
        "progress_pct": progress_pct,
        "roadmap_status": roadmap_phase["status"] if roadmap_phase else "developing",
        "scope": roadmap_phase["scope"] if roadmap_phase else [],
        "acceptance_criteria": roadmap_phase["acceptance_criteria"] if roadmap_phase else [],
        "evidence_packet": evidence_packet,
        "next_actions": next_actions,
        "capability_kind": "development_safe_slice",
        "production_capability": False,
        "execution_available": False,
        "real_broker_call_allowed": False,
        "wallet_signing_available": False,
    }


def research_report_payload(report: ResearchReport | None) -> dict[str, Any] | None:
    if report is None:
        return None
    return {
        "id": report.id,
        "report_type": report.report_type,
        "agent_name": report.agent_name,
        "data_snapshot_id": report.data_snapshot_id,
        "asset_id": report.asset_id,
        "suggested_action": report.suggested_action,
        "confidence": float(report.confidence),
        "has_evidence": bool(report.evidence),
        "created_at": report.created_at,
        "execution_available": False,
    }


def thesis_delta_payload(report: ResearchReport | None, active_theses: int) -> dict[str, Any]:
    if report is None:
        return {
            "status": "missing_report",
            "active_theses_count": active_theses,
            "summary": "No research report exists to compare against active theses.",
            "execution_available": False,
        }
    return {
        "status": "requires_review",
        "active_theses_count": active_theses,
        "latest_report_asset_id": report.asset_id,
        "suggested_action": report.suggested_action,
        "summary": "Treat research output as evidence until a human reviews thesis delta.",
        "execution_available": False,
    }


def phase_check(key: str, passed: bool, summary: str) -> dict[str, Any]:
    return {
        "key": key,
        "passed": passed,
        "status": "ok" if passed else "block",
        "summary": summary,
    }
