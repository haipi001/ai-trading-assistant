from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import BacktestRun
from app.models import DataCatalogEntry
from app.models import DataSourceConnection
from app.models import ExportArtifact
from app.models import InvestmentLedgerEntry
from app.models import OperationalEvent
from app.models import OrderDraft
from app.models import ProductionReadinessTarget
from app.models import ReconciliationRun
from app.models import ResearchReport
from app.models import SecretReference
from app.models import UserAccount


class FundraisingReadinessService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def summary(self, *, user_id: str = "default-user") -> dict[str, Any]:
        items = self.items(user_id=user_id)
        progress = round(sum(item["progress_pct"] for item in items) / len(items))
        blockers = [blocker for item in items for blocker in item["blockers"]]
        ready_items = [item for item in items if item["financing_status"] == "ready"]
        return {
            "status": "developed_safe_slice",
            "financing_status": "blocked" if blockers else "ready",
            "target": "RMB_10M_plus_seed_style",
            "progress_pct": progress,
            "developed_items": len(items),
            "ready_items": len(ready_items),
            "blocked_items": len(items) - len(ready_items),
            "execution_available": False,
            "capability_kind": "preflight_capability",
            "production_capability": False,
            "capability_boundary": "Readiness summaries, reports, and packets are preflight evidence only; they do not certify production launch or unlock execution.",
            "production_unlock_requires": [
                "real authenticated read-only data proof",
                "trusted ledger reconciliation",
                "auth/RBAC/secrets/monitoring/backups",
                "legal and operational release approval",
            ],
            "live_trading_enabled": self.settings.live_trading_enabled,
            "real_broker_call_allowed": False,
            "autonomous_trading_added": False,
            "blockers": blockers[:12],
            "next_actions": [
                "Use this packet as the financing-readiness development queue.",
                "Start with item 1 and keep later items gated until the earlier evidence is stronger.",
                "Keep live execution behind sandbox, approval, reconciliation, and kill-switch proof.",
            ],
            "items": items,
        }

    def items(self, *, user_id: str = "default-user") -> list[dict[str, Any]]:
        return [
            self.icp_killer_workflow(user_id=user_id),
            self.real_readonly_data(user_id=user_id),
            self.production_controls(user_id=user_id),
            self.compliance_boundary(user_id=user_id),
            self.ai_trust_layer(user_id=user_id),
            self.beta_traction(user_id=user_id),
            self.investor_demo_path(user_id=user_id),
            self.business_model_gtm(user_id=user_id),
            self.fundraising_data_room(user_id=user_id),
            self.controlled_sandbox_proof(user_id=user_id),
        ]

    def item(self, item_no: int, *, user_id: str = "default-user") -> dict[str, Any]:
        for item in self.items(user_id=user_id):
            if item["item_no"] == item_no:
                return item
        raise ValueError("fundraising readiness item not found")

    def icp_killer_workflow(self, *, user_id: str) -> dict[str, Any]:
        _ = user_id
        return self._packet(
            item_no=1,
            key="icp_killer_workflow",
            title="ICP and killer workflow",
            progress_pct=55,
            financing_status="needs_evidence",
            completed=[
                "Product wedge is captured as a self-discipline financial terminal, not a black-box trading bot.",
                "Financing readiness packet now forces one ICP, one activation metric, and one retention metric.",
            ],
            blockers=[
                "beachhead_icp_not_signed_off",
                "primary_activation_metric_not_instrumented",
                "weekly_retention_metric_not_instrumented",
            ],
            warnings=["Current market definition is still broader than a seed-stage wedge."],
            next_actions=[
                "Choose one beachhead: active multi-asset self-directed investor, crypto/equity operator, or analyst-like power user.",
                "Write a one-sentence workflow promise and map the first-session activation event.",
                "Reject features that do not strengthen that daily workflow before the financing demo.",
            ],
            evidence=[
                "PROJECT_BRIEF wedge and mandatory thesis-to-review flow.",
                "FUNDRAISING_READINESS_GAP_ANALYSIS_2026_06_19.md item 1.",
            ],
        )

    def real_readonly_data(self, *, user_id: str) -> dict[str, Any]:
        readonly_connections = self._count(
            DataSourceConnection,
            DataSourceConnection.mode == "read_only",
        )
        authenticated_candidates = self._count(
            DataSourceConnection,
            DataSourceConnection.mode == "read_only",
            DataSourceConnection.credentials_ref.is_not(None),
        )
        trusted_datasets = self._count(DataCatalogEntry, DataCatalogEntry.quality_status == "VALID")
        blockers = []
        if authenticated_candidates == 0:
            blockers.append("authenticated_readonly_adapter_missing")
        if trusted_datasets == 0:
            blockers.append("trusted_dataset_missing")
        return self._packet(
            item_no=2,
            key="real_authenticated_readonly_data",
            title="Real authenticated read-only account data",
            progress_pct=45 if authenticated_candidates else 35,
            financing_status="blocked" if blockers else "review_ready",
            completed=[
                "Read-only setup and certification surfaces exist.",
                "Data catalog and contract enforcement surfaces exist.",
                "This packet now reports whether authenticated read-only evidence exists.",
            ],
            blockers=blockers,
            warnings=["Sample payloads are acceptable for demo scaffolding but weak for financing proof."],
            next_actions=[
                "Implement exactly one real read-only broker or CEX adapter first.",
                "Store only a secret reference; reject inline keys and any withdrawal or trading capability.",
                "Sync positions, balances, transactions, freshness, and reconciliation status.",
            ],
            evidence=[
                f"read_only_connections={readonly_connections}",
                f"connections_with_credentials_ref={authenticated_candidates}",
                f"valid_catalog_datasets={trusted_datasets}",
            ],
            metrics={
                "read_only_connections": readonly_connections,
                "connections_with_credentials_ref": authenticated_candidates,
                "valid_catalog_datasets": trusted_datasets,
            },
        )

    def production_controls(self, *, user_id: str) -> dict[str, Any]:
        targets = self._target_counts(user_id)
        secret_refs = self._count(SecretReference, SecretReference.user_id == user_id)
        required = ["auth", "rbac", "secrets", "monitoring", "backup", "restore_drill", "audit_retention"]
        missing = [key for key in required if targets.get(key, 0) == 0]
        if secret_refs == 0:
            missing.append("secret_reference_registry")
        return self._packet(
            item_no=3,
            key="production_auth_rbac_secrets_ops",
            title="Production auth, RBAC, secrets, monitoring, backup, restore drill",
            progress_pct=40 if len(missing) < len(required) else 30,
            financing_status="blocked" if missing else "review_ready",
            completed=[
                "Beta readiness, secret-reference, operational-event, restore-drill, and production-target metadata surfaces exist.",
                "This packet maps those surfaces to financing diligence controls.",
            ],
            blockers=missing,
            warnings=["Production targets are metadata until external providers are wired and drills are executed."],
            next_actions=[
                "Record production targets for auth, RBAC, secrets, monitoring, backups, restore drills, and audit retention.",
                "Run an isolated restore drill before external beta.",
                "Wire one real monitoring/error-reporting provider before storing real read-only account data.",
            ],
            evidence=[f"production_targets={targets}", f"secret_references={secret_refs}"],
            metrics={**targets, "secret_references": secret_refs},
        )

    def compliance_boundary(self, *, user_id: str) -> dict[str, Any]:
        targets = self._target_counts(user_id)
        required = ["legal_memo", "disclaimer", "marketing_claims_policy", "ai_output_policy", "privacy_policy"]
        missing = [key for key in required if targets.get(key, 0) == 0]
        return self._packet(
            item_no=4,
            key="external_compliance_boundary",
            title="External-readable compliance boundary and legal memo",
            progress_pct=35,
            financing_status="blocked" if missing else "review_ready",
            completed=[
                "Safety docs already prohibit investment-adviser, profit-promise, and autonomous-bot positioning.",
                "This packet turns those internal rules into an investor diligence checklist.",
            ],
            blockers=missing,
            warnings=["This is not legal advice; a qualified counsel review is still required before public launch."],
            next_actions=[
                "Create an external legal/compliance memo for the first jurisdiction.",
                "Lock product copy around workflow automation and self-discipline, not personalized advice or return promises.",
                "Add user acknowledgements for AI limitations, data quality, and no live execution.",
            ],
            evidence=["docs/SAFETY_AND_RISK.md", "docs/FUNDRAISING_READINESS_GAP_ANALYSIS_2026_06_19.md"],
        )

    def ai_trust_layer(self, *, user_id: str) -> dict[str, Any]:
        reports = self._count(ResearchReport)
        eval_events = self._count(
            OperationalEvent,
            OperationalEvent.user_id == user_id,
            OperationalEvent.event_type.in_(["ai_eval", "ai_red_team", "ai_provider_check"]),
        )
        blockers = []
        if not self.settings.external_llm_calls_enabled or self.settings.ai_provider_default == "mock":
            blockers.append("real_llm_provider_not_enabled")
        if eval_events == 0:
            blockers.append("ai_eval_events_missing")
        return self._packet(
            item_no=5,
            key="ai_provider_eval_citation_antihallucination",
            title="Real AI provider, evals, citations, and anti-hallucination controls",
            progress_pct=45 if reports else 35,
            financing_status="blocked" if blockers else "review_ready",
            completed=[
                "Mock AI/reporting and provider-status boundaries exist.",
                "This packet makes eval, citation, and hallucination control explicit financing gates.",
            ],
            blockers=blockers,
            warnings=["A real provider should stay disabled until evals and order-leakage tests are in place."],
            next_actions=[
                "Implement a safe external LLM adapter with no broker/exchange/wallet permissions.",
                "Add eval cases for stale data, unsupported claims, hallucination, and executable-order leakage.",
                "Require evidence packets and source citations for research conclusions.",
            ],
            evidence=[
                f"research_reports={reports}",
                f"ai_eval_events={eval_events}",
                f"default_provider={self.settings.ai_provider_default}",
            ],
            metrics={"research_reports": reports, "ai_eval_events": eval_events},
        )

    def beta_traction(self, *, user_id: str) -> dict[str, Any]:
        users = self._count(UserAccount)
        traction_events = self._count(
            OperationalEvent,
            OperationalEvent.user_id == user_id,
            OperationalEvent.event_type.in_(["beta_user_interview", "pilot_loi", "paid_intent", "retention_checkpoint"]),
        )
        blockers = []
        if users < 10:
            blockers.append("beta_user_count_below_10")
        if traction_events == 0:
            blockers.append("traction_evidence_missing")
        return self._packet(
            item_no=6,
            key="beta_users_retention_paid_intent_loi",
            title="Beta users, retention, paid intent, and LOIs",
            progress_pct=35 if users else 20,
            financing_status="blocked" if blockers else "review_ready",
            completed=[
                "Beta readiness and invitation packet surfaces exist.",
                "This packet adds traction evidence as a financing gate instead of a vague future task.",
            ],
            blockers=blockers,
            warnings=["Local demo users do not count as traction unless tied to interviews, retention, or paid intent."],
            next_actions=[
                "Recruit 10-30 tightly matched beta users.",
                "Track activation, weekly use, thesis review completion, and account sync repetition.",
                "Collect 3-5 pilot/LOI or paid-intent artifacts before a serious raise.",
            ],
            evidence=[f"user_accounts={users}", f"traction_events={traction_events}"],
            metrics={"user_accounts": users, "traction_events": traction_events},
        )

    def investor_demo_path(self, *, user_id: str) -> dict[str, Any]:
        order_drafts = self._count(OrderDraft)
        ledgers = self._count(InvestmentLedgerEntry, InvestmentLedgerEntry.user_id == user_id)
        reviews = self._count(OperationalEvent, OperationalEvent.event_type == "demo_rehearsal")
        blockers = []
        if order_drafts == 0:
            blockers.append("demo_order_draft_missing")
        if ledgers == 0:
            blockers.append("demo_ledger_evidence_missing")
        if reviews == 0:
            blockers.append("seven_minute_demo_rehearsal_missing")
        return self._packet(
            item_no=7,
            key="seven_minute_investor_demo_path",
            title="Investor 7-minute understandable demo path",
            progress_pct=60 if order_drafts else 45,
            financing_status="blocked" if blockers else "review_ready",
            completed=[
                "Official demo flow, seed status, order draft, paper execution, journal, and review surfaces already exist.",
                "This packet sequences the demo around investor comprehension rather than endpoint coverage.",
            ],
            blockers=blockers,
            warnings=["A founder-led demo is strong only if it can run without explaining internal architecture first."],
            next_actions=[
                "Script the demo as: connect/read data, see thesis, detect violation, gate draft, paper fill, review lesson.",
                "Add a demo rehearsal operational event after the script runs end-to-end.",
                "Keep the final screen on financing readiness, not live trading.",
            ],
            evidence=[f"order_drafts={order_drafts}", f"ledger_entries={ledgers}", f"demo_rehearsals={reviews}"],
            metrics={"order_drafts": order_drafts, "ledger_entries": ledgers, "demo_rehearsals": reviews},
        )

    def business_model_gtm(self, *, user_id: str) -> dict[str, Any]:
        targets = self._target_counts(user_id)
        required = ["pricing", "gtm_channel", "sales_funnel", "unit_economics"]
        missing = [key for key in required if targets.get(key, 0) == 0]
        return self._packet(
            item_no=8,
            key="business_model_pricing_gtm",
            title="Business model, pricing, and GTM",
            progress_pct=25,
            financing_status="blocked" if missing else "review_ready",
            completed=[
                "This packet converts commercial strategy into trackable production-readiness targets.",
            ],
            blockers=missing,
            warnings=["A broad multi-asset narrative needs one concrete channel before fundraising."],
            next_actions=[
                "Choose first pricing model: pro terminal subscription, team workspace, or self-hosted license.",
                "Write one channel plan with CAC hypothesis and conversion stages.",
                "Add willingness-to-pay evidence from beta calls or pilot prospects.",
            ],
            evidence=[f"production_targets={targets}"],
        )

    def fundraising_data_room(self, *, user_id: str) -> dict[str, Any]:
        targets = self._target_counts(user_id)
        exports = self._count(ExportArtifact, ExportArtifact.user_id == user_id)
        required = ["deck", "one_pager", "demo_video", "data_room", "financial_model", "hiring_plan"]
        missing = [key for key in required if targets.get(key, 0) == 0]
        return self._packet(
            item_no=9,
            key="deck_onepager_demo_video_data_room",
            title="Deck, one-pager, demo video, and data room",
            progress_pct=30,
            financing_status="blocked" if missing else "review_ready",
            completed=[
                "Fundraising readiness analysis document exists.",
                "This packet defines the investor materials checklist.",
            ],
            blockers=missing,
            warnings=["Product docs are not a substitute for a crisp investor packet."],
            next_actions=[
                "Create a 10-12 slide deck, one-page memo, and 90-second demo video.",
                "Add architecture, safety, compliance, metrics, and use-of-funds folders to the data room.",
                "Export a current product-readiness snapshot before outreach.",
            ],
            evidence=[f"export_artifacts={exports}", f"production_targets={targets}"],
            metrics={"export_artifacts": exports},
        )

    def controlled_sandbox_proof(self, *, user_id: str) -> dict[str, Any]:
        _ = user_id
        live_configs = self._count(LiveExecutionConfigProxy.model())
        reconciliations = self._count(ReconciliationRun)
        blockers = ["real_sandbox_adapter_missing", "signed_approval_packet_missing"]
        if live_configs == 0:
            blockers.append("sandbox_config_missing")
        if reconciliations == 0:
            blockers.append("order_state_reconciliation_missing")
        return self._packet(
            item_no=10,
            key="controlled_live_sandbox_proof",
            title="Controlled sandbox proof while live stays postponed",
            progress_pct=40,
            financing_status="blocked",
            completed=[
                "Live execution prepare, sandbox-run, broker reconciliation plan, small pilot readiness, and go/no-go packets exist.",
                "This packet keeps real submission disabled and frames sandbox proof as the only acceptable next step.",
            ],
            blockers=blockers,
            warnings=["Do not make live execution the financing dependency; it should remain a controlled option."],
            next_actions=[
                "Implement a broker sandbox adapter that cannot touch production accounts.",
                "Add explicit account allowlist, idempotency keys, cancel path, and rollback drill.",
                "Require signed approval packet and successful reconciliation before any small pilot.",
            ],
            evidence=[f"live_configs={live_configs}", f"reconciliation_runs={reconciliations}"],
            metrics={"live_configs": live_configs, "reconciliation_runs": reconciliations},
        )

    def _packet(
        self,
        *,
        item_no: int,
        key: str,
        title: str,
        progress_pct: int,
        financing_status: str,
        completed: list[str],
        blockers: list[str],
        warnings: list[str],
        next_actions: list[str],
        evidence: list[str],
        metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "item_no": item_no,
            "key": key,
            "title": title,
            "development_status": "developed_safe_slice",
            "financing_status": financing_status,
            "progress_pct": progress_pct,
            "completed_in_this_pass": completed,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": next_actions,
            "evidence": evidence,
            "metrics": metrics or {},
            "execution_available": False,
            "capability_kind": "preflight_capability",
            "production_capability": False,
            "capability_boundary": "This readiness packet is a preflight development/evidence checklist, not a production capability.",
            "live_execution_enabled": False,
            "real_broker_call_allowed": False,
            "wallet_signing_available": False,
            "cex_trading_available": False,
        }

    def _count(self, model: Any, *conditions: Any) -> int:
        statement = select(func.count()).select_from(model)
        for condition in conditions:
            statement = statement.where(condition)
        return int(self.db.scalar(statement) or 0)

    def _target_counts(self, user_id: str) -> dict[str, int]:
        rows = self.db.execute(
            select(ProductionReadinessTarget.target_type, func.count())
            .where(ProductionReadinessTarget.user_id == user_id)
            .group_by(ProductionReadinessTarget.target_type)
        ).all()
        return {str(key): int(count) for key, count in rows}


class LiveExecutionConfigProxy:
    @staticmethod
    def model() -> Any:
        from app.models import LiveExecutionConfig

        return LiveExecutionConfig
