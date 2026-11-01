from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import BacktestRun
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import DataSourceConnection
from app.models import DecisionGate
from app.models import ExportArtifact
from app.models import InvestmentLedgerEntry
from app.models import InvestmentThesis
from app.models import LocalUserConfig
from app.models import OperationalEvent
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PostTradeReview
from app.models import ProductionReadinessTarget
from app.models import ReconciliationRun
from app.models import Reminder
from app.models import ResearchReport
from app.models import ScheduledJob
from app.models import SecretReference
from app.models import StrategyRule
from app.models import UserAccount
from app.models import WatchlistItem
from app.models import WorkflowReviewTask


class CompleteProductReadinessService:
    def __init__(self, db: Session):
        self.db = db
        self.schema_warnings: list[str] = []

    def summary(self, *, user_id: str = "default-user") -> dict[str, Any]:
        items = self.items(user_id=user_id)
        progress = round(sum(item["progress_pct"] for item in items) / len(items))
        blockers = [blocker for item in items for blocker in item["blockers"]]
        ready_items = [item for item in items if item["product_status"] == "ready"]
        return {
            "status": "developed_safe_slice",
            "product_status": "blocked" if blockers else "ready",
            "target": "complete_personal_financial_terminal",
            "progress_pct": progress,
            "developed_items": len(items),
            "ready_items": len(ready_items),
            "blocked_items": len(items) - len(ready_items),
            "execution_available": False,
            "capability_kind": "preflight_capability",
            "production_capability": False,
            "capability_boundary": "Readiness/report/packet surfaces are preflight capability maps only; production capability must be proven by authenticated data, reconciliation, operations, legal, and release gates.",
            "production_unlock_requires": [
                "Founder daily-use loop",
                "real authenticated read-only data",
                "trusted ledger and data promotion",
                "private beta controls",
                "broker sandbox audit proof before any pilot",
            ],
            "real_broker_call_allowed": False,
            "wallet_signing_available": False,
            "cex_trading_available": False,
            "blockers": blockers[:20],
            "next_actions": [
                "Treat this as the full-product development queue after financing readiness.",
                "Optimize for a daily, easy-to-start user loop before adding more advanced automation.",
                "Keep execution-stack work last; the product must be valuable without live trading.",
            ],
            "items": items,
        }

    def items(self, *, user_id: str = "default-user") -> list[dict[str, Any]]:
        targets = self._target_counts(user_id)
        counts = self._counts(user_id)
        packets = [
            self._daily_loop(counts),
            self._investment_ledger(counts),
            self._data_trust(counts),
            self._research_terminal(counts),
            self._portfolio_management(counts),
            self._strategy_backtest(counts),
            self._decision_gate_explainability(counts),
            self._journal_review(counts),
            self._notifications_calendar(counts),
            self._user_system(counts, targets),
            self._commercialization(counts, targets),
            self._product_ops_admin(counts, targets),
            self._security_engineering(counts, targets),
            self._ai_safety(counts),
            self._ai_governance(counts, targets),
            self._deployment_operability(counts, targets),
            self._testing_system(counts, targets),
            self._frontend_experience(counts, targets),
            self._open_ecosystem(counts, targets),
            self._execution_stack(counts),
        ]
        packets = self._apply_product_completion(packets, user_id=user_id)
        if self.schema_warnings:
            warnings = sorted(set(self.schema_warnings))
            packets[15]["blockers"].extend([f"schema_unavailable:{name}" for name in warnings])
            packets[15]["product_status"] = "blocked"
            packets[15]["metrics"] = {**packets[15]["metrics"], "schema_warnings": warnings}
        return packets

    def _apply_product_completion(self, packets: list[dict[str, Any]], *, user_id: str) -> list[dict[str, Any]]:
        try:
            configured = {
                item.config_key.removeprefix("product_completion:")
                for item in self.db.scalars(
                    select(LocalUserConfig).where(
                        LocalUserConfig.user_id == user_id,
                        LocalUserConfig.config_key.like("product_completion:%"),
                    )
                ).all()
            }
        except (SQLAlchemyError, AttributeError):
            self.schema_warnings.append(LocalUserConfig.__tablename__)
            configured = set()
        improvements = {
            1: ("daily_loop", 70, {"daily_workflow_scheduling_missing"}, {"daily_user_onboarding_completion_required"}),
            2: ("ledger", 65, {"multi_currency_cash_ledger_missing", "corporate_action_normalization_incomplete"}, set()),
            3: ("data_trust", 65, {"dataset_versioning_missing", "snapshot_replay_missing", "provider_fallback_policy_missing"}, set()),
            4: ("research", 55, set(), {"real_research_event_providers_missing"}),
            5: ("portfolio_risk", 60, {"factor_exposure_missing", "correlation_and_liquidity_risk_missing", "scenario_stress_tests_missing"}, set()),
            9: ("daily_loop", 40, {"unhandled_item_escalation_missing"}, set()),
            10: ("users_commercial", 45, {"multi_device_sessions_missing"}, set()),
            11: ("users_commercial", 40, {"plan_limits_missing", "usage_metering_missing", "customer_support_console_missing"}, {"live_payment_provider_missing"}),
            12: ("users_commercial", 45, {"invite_code_management_missing", "feedback_inbox_missing"}, set()),
            13: ("production_ops", 40, {"dependency_scanning_missing", "incident_response_incomplete"}, set()),
            14: ("research", 55, {"model_output_validation_incomplete", "eval_dashboard_missing"}, set()),
            15: ("research", 50, {"eval_versioning_missing", "ai_output_provenance_incomplete"}, set()),
            16: ("production_ops", 45, {"migration_rollback_missing", "slo_sla_error_budget_missing"}, {"external_observability_and_managed_restore_missing"}),
            17: ("production_ops", 65, {"frontend_e2e_main_paths_incomplete", "visual_regression_missing", "recovery_drill_tests_missing"}, {"immutable_ci_evidence_missing"}),
            18: ("daily_loop", 65, {"accessibility_keyboard_nav_incomplete", "mobile_review_flow_incomplete"}, set()),
            20: ("external_proof", 60, {"broker_sandbox_adapter_missing", "execution_order_state_machine_incomplete", "idempotency_cancel_replace_missing", "post_execution_reconciliation_incomplete"}, {"real_broker_sandbox_evidence_missing"}),
        }
        for packet in packets:
            improvement = improvements.get(packet["item_no"])
            if not improvement:
                continue
            config_key, progress, resolved, added = improvement
            if config_key not in configured:
                continue
            packet["progress_pct"] = max(packet["progress_pct"], progress)
            packet["blockers"] = [blocker for blocker in packet["blockers"] if blocker not in resolved]
            packet["blockers"].extend(sorted(added - set(packet["blockers"])))
            if packet["item_no"] == 4 and packet["metrics"].get("research_feed_types_ready") == 4 and packet["metrics"].get("catalyst_calendars", 0) > 0:
                packet["blockers"] = [blocker for blocker in packet["blockers"] if blocker != "real_research_event_providers_missing"]
            packet["completed_in_this_pass"] = [
                *packet["completed_in_this_pass"],
                f"Product completion slice initialized: {config_key}.",
            ]
            packet["metrics"] = {**packet["metrics"], "product_completion_initialized": True}
            packet["product_status"] = "ready" if not packet["blockers"] else "blocked"
        try:
            risk_artifact = self.db.scalar(
                select(ExportArtifact)
                .where(
                    ExportArtifact.user_id == user_id,
                    ExportArtifact.export_type == "portfolio_time_series_risk",
                )
                .order_by(ExportArtifact.created_at.desc(), ExportArtifact.id.desc())
                .limit(1)
            )
        except SQLAlchemyError:
            self.schema_warnings.append(ExportArtifact.__tablename__)
            risk_artifact = None
        if risk_artifact is not None:
            packet = next(item for item in packets if item["item_no"] == 5)
            resolved = {
                "correlation_and_liquidity_risk_missing",
                "scenario_stress_tests_missing",
                "drawdown_budget_consumption_missing",
            }
            packet["blockers"] = [blocker for blocker in packet["blockers"] if blocker not in resolved]
            packet["progress_pct"] = max(packet["progress_pct"], 75)
            packet["completed_in_this_pass"] = [
                *packet["completed_in_this_pass"],
                "Real daily-return correlation, VaR/ES, drawdown budget, liquidity, and stress evidence are available.",
            ]
            packet["metrics"] = {
                **packet["metrics"],
                "time_series_risk_artifact_id": risk_artifact.id,
                "time_series_risk_status": risk_artifact.summary_json.get("status"),
                "time_series_coverage_pct": risk_artifact.summary_json.get("coverage_pct"),
                "time_series_observations": risk_artifact.summary_json.get("observations"),
            }
            packet["product_status"] = "ready" if not packet["blockers"] else "blocked"
        try:
            onboarding_config = self.db.scalar(
                select(LocalUserConfig).where(
                    LocalUserConfig.user_id == user_id,
                    LocalUserConfig.config_key == "founder_onboarding",
                ).limit(1)
            )
            local_start_config = self.db.scalar(
                select(LocalUserConfig).where(
                    LocalUserConfig.user_id == user_id,
                    LocalUserConfig.config_key == "local_start",
                ).limit(1)
            )
        except SQLAlchemyError:
            onboarding_config = None
            local_start_config = None
        onboarding_state = dict(onboarding_config.value_json or {}) if onboarding_config is not None else {}
        onboarding_required = {
            "workspace_goal",
            "risk_boundary_acknowledged",
            "read_only_data_plan",
            "daily_review_time",
            "first_daily_open",
        }
        onboarding_complete = (
            all(bool(onboarding_state.get(key)) for key in onboarding_required)
            and onboarding_state.get("risk_boundary_acknowledged") is True
            and local_start_config is not None
            and bool((local_start_config.value_json or {}).get("initialized"))
        )
        if onboarding_complete:
            packet = next(item for item in packets if item["item_no"] == 1)
            packet["blockers"] = [
                blocker for blocker in packet["blockers"]
                if blocker != "daily_user_onboarding_completion_required"
            ]
            packet["progress_pct"] = max(packet["progress_pct"], 85)
            packet["completed_in_this_pass"] = [
                *packet["completed_in_this_pass"],
                "Founder onboarding, risk acknowledgement, data mode, review cadence, and first daily open are complete.",
            ]
            packet["metrics"] = {
                **packet["metrics"],
                "onboarding_completed_steps": len(onboarding_required),
                "onboarding_required_steps": len(onboarding_required),
                "local_start_initialized": True,
            }
            packet["product_status"] = "ready" if not packet["blockers"] else "blocked"
        try:
            research_intents = list(
                self.db.scalars(
                    select(OrderIntent)
                    .join(InvestmentThesis, InvestmentThesis.id == OrderIntent.investment_thesis_id)
                    .where(OrderIntent.source_type == "research_report")
                    .where(InvestmentThesis.user_id == user_id)
                    .order_by(OrderIntent.created_at.desc(), OrderIntent.id.desc())
                    .limit(100)
                ).all()
            )
            traced_intent = next(
                (
                    item for item in research_intents
                    if item.evidence_json.get("research_report_id")
                    and item.evidence_json.get("data_snapshot_id")
                    and item.evidence_json.get("thesis_checkpoint_id")
                ),
                None,
            )
            trace_gates = list(
                self.db.scalars(
                    select(DecisionGate).where(DecisionGate.order_intent_id == traced_intent.id)
                ).all()
            ) if traced_intent is not None else []
        except (SQLAlchemyError, AttributeError):
            traced_intent = None
            trace_gates = []
        gate_types = {gate.gate_type for gate in trace_gates if gate.evidence_json.get("order_trace")}
        if traced_intent is not None and {"RESEARCH_GATE", "THESIS_GATE"}.issubset(gate_types):
            packet = next(item for item in packets if item["item_no"] == 4)
            packet["blockers"] = [
                blocker for blocker in packet["blockers"]
                if blocker != "research_to_order_traceability_incomplete"
            ]
            packet["progress_pct"] = max(packet["progress_pct"], 80)
            packet["completed_in_this_pass"] = [
                *packet["completed_in_this_pass"],
                "Research report, source snapshot, human thesis checkpoint, plan intent, and gate evidence are trace-linked.",
            ]
            packet["metrics"] = {
                **packet["metrics"],
                "traced_order_intent_id": traced_intent.id,
                "trace_gate_types": sorted(gate_types),
                "research_report_id": traced_intent.evidence_json.get("research_report_id"),
                "thesis_checkpoint_id": traced_intent.evidence_json.get("thesis_checkpoint_id"),
            }
            packet["product_status"] = "ready" if not packet["blockers"] else "blocked"
        return packets

    def item(self, item_no: int, *, user_id: str = "default-user") -> dict[str, Any]:
        for item in self.items(user_id=user_id):
            if item["item_no"] == item_no:
                return item
        raise ValueError("complete product readiness item not found")

    def _daily_loop(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = []
        if counts["reminders"] == 0:
            blockers.append("review_reminders_missing")
        if counts["watchlist_items"] == 0:
            blockers.append("watchlist_missing")
        if counts["scheduled_jobs"] == 0:
            blockers.append("daily_workflow_scheduling_missing")
        return self._packet(
            1,
            "daily_use_loop",
            "True daily-use loop",
            "The user should open the terminal and immediately know what to inspect, update, decide, or review.",
            "Reduce every day to one guided path: check data, inspect exceptions, update thesis, decide, review.",
            "Use a single today queue with clear states, next buttons, and no architecture jargon.",
            50,
            blockers,
            ["Daily action queue, reminders, watchlist, and local backup/export surfaces exist."],
            ["Add first-run onboarding and open/close workflow templates.", "Auto-schedule thesis checkpoints and stale-data reviews.", "Show abnormal states with one next action each."],
            counts,
        )

    def _investment_ledger(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = []
        if counts["ledger_entries"] == 0:
            blockers.append("ledger_entries_missing")
        if counts["reconciliation_runs"] == 0:
            blockers.append("reconciliation_runs_missing")
        blockers.extend(["multi_currency_cash_ledger_missing", "corporate_action_normalization_incomplete", "automatic_statement_download_missing"])
        return self._packet(
            2,
            "complete_investment_ledger",
            "Complete investment ledger",
            "The user must trust the portfolio memory before trusting any decision or review.",
            "Ledger is the source of memory; positions are derived views, not hand-wavy balances.",
            "Expose ledger trust, breaks, repair actions, and PnL explanations next to holdings.",
            45,
            blockers,
            ["Ledger sync, statement import, extended reconciliation, tax-lot and corporate-action checks have safe slices."],
            ["Add multi-currency cash and FX records.", "Normalize dividends, splits, fees, interest, airdrops, and transfers.", "Build reconciliation repair workflow before data promotion."],
            counts,
        )

    def _data_trust(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = []
        if counts["catalog_entries"] == 0:
            blockers.append("data_catalog_entries_missing")
        if counts["quality_reports"] == 0:
            blockers.append("data_quality_reports_missing")
        blockers.extend(["dataset_versioning_missing", "snapshot_replay_missing", "provider_fallback_policy_missing", "entitlements_missing"])
        return self._packet(
            3,
            "deep_data_trust",
            "Deeper data trust system",
            "The user should never wonder whether a number is stale, delayed, incomplete, or approved for decisions.",
            "Every downstream decision inherits source, timestamp, quality, permissions, and promotion status.",
            "Put trust badges, lineage drilldowns, and replay buttons directly on data-dependent panels.",
            45,
            blockers,
            ["Data catalog, trust report, freshness, and contract enforcement safe slices exist."],
            ["Persist raw payload hashes and dataset versions.", "Add snapshot replay and provider fallback/rate-limit policy.", "Carry realtime/delayed/stale and entitlement status through gates and drafts."],
            counts,
        )

    def _research_terminal(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["news_fundamentals_macro_onchain_event_feeds_missing", "catalyst_calendar_missing", "research_to_order_traceability_incomplete"]
        feed_types = {"news", "sec_filings_fundamentals", "macro_series", "onchain_metrics"}
        try:
            ready_feed_types = set(self.db.scalars(select(DataSnapshot.snapshot_type).where(DataSnapshot.snapshot_type.in_(feed_types)).distinct()).all())
            catalyst_count = self._count(DataSnapshot, DataSnapshot.snapshot_type == "catalyst_calendar")
        except (SQLAlchemyError, AttributeError):
            self.schema_warnings.append(DataSnapshot.__tablename__)
            ready_feed_types = set()
            catalyst_count = 0
        if ready_feed_types == feed_types:
            blockers.remove("news_fundamentals_macro_onchain_event_feeds_missing")
        if catalyst_count:
            blockers.remove("catalyst_calendar_missing")
        if counts["research_reports"] == 0:
            blockers.append("research_reports_missing")
        if counts["theses"] == 0:
            blockers.append("investment_theses_missing")
        return self._packet(
            4,
            "research_terminal_depth",
            "Research engine that feels like a terminal",
            "The user needs to understand what changed since the thesis, not read generic AI prose.",
            "Research starts from position context and ends in evidence-backed thesis deltas.",
            "Show event streams, evidence packets, and memo templates beside each holding/thesis.",
            70 if ready_feed_types == feed_types and catalyst_count else 40,
            blockers,
            ["Research reports, thesis capture/monitor, and mock research committee exist.", "Real public news, SEC, macro, on-chain, and catalyst snapshots are available." if ready_feed_types == feed_types and catalyst_count else "Research feed contracts are available."],
            ["Add news, filings, earnings, macro, and on-chain event feeds.", "Build thesis delta detection and catalyst calendar.", "Link research conclusions to order-draft rationale and gate evidence."],
            {**counts, "research_feed_types_ready": len(ready_feed_types), "catalyst_calendars": catalyst_count},
        )

    def _portfolio_management(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["factor_exposure_missing", "correlation_and_liquidity_risk_missing", "scenario_stress_tests_missing", "drawdown_budget_consumption_missing"]
        return self._packet(
            5,
            "portfolio_management_depth",
            "Portfolio management depth",
            "The user needs to see portfolio risk as a system, not just a list of positions.",
            "Portfolio view should translate holdings into exposures, fragility, and budget consumption.",
            "Make allocation, concentration, counterparty, stablecoin, DeFi, and drawdown visible at a glance.",
            35,
            blockers,
            ["Portfolio current, snapshots, daily summary, Web3 read-only risk, and risk budgets exist."],
            ["Add allocation, sector/theme/factor exposure, and correlation views.", "Add counterparty/exchange and stablecoin/DeFi/wallet exposure summaries.", "Add scenario stress tests and risk-budget burn-down."],
            counts,
        )

    def _strategy_backtest(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["strategy_dsl_too_limited", "multi_asset_backtest_missing", "walk_forward_missing", "promotion_to_paper_workflow_missing"]
        if counts["backtest_runs"] == 0:
            blockers.append("backtest_runs_missing")
        return self._packet(
            6,
            "strategy_backtest_lab_depth",
            "Deeper strategy and backtest lab",
            "The user should test a strategy before trusting a rule, and know why not to promote it.",
            "Backtests are research evidence, not execution authority.",
            "Show benchmark, sensitivity, slippage, liquidity, and promotion blockers in one research packet.",
            40,
            blockers,
            ["Strategy rules, deterministic backtest runs, promotion preflight, and research packets exist."],
            ["Add richer strategy DSL and multi-asset runs.", "Add benchmark, walk-forward, out-of-sample, slippage and liquidity models.", "Add gated promotion from backtest to paper trading only."],
            counts,
        )

    def _decision_gate_explainability(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["gate_replay_missing", "gate_policy_versioning_missing", "override_capture_missing", "workflow_enforcement_incomplete"]
        if counts["decision_gates"] == 0:
            blockers.append("decision_gates_missing")
        return self._packet(
            7,
            "decision_gate_explainability",
            "Decision gate explainability",
            "The user must understand why the system says yes, warns, or blocks.",
            "Every gate decision should be replayable with versioned policy and evidence.",
            "Put gate evidence, override reasons, and order-closure drilldowns inside the approval flow.",
            50,
            blockers,
            ["Decision gates, stage readiness, order-closure report, and workflow state machine exist."],
            ["Add gate replay and evidence chain drilldowns.", "Version gate policies and capture user overrides.", "Enforce workflow transitions instead of only reporting readiness."],
            counts,
        )

    def _journal_review(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["single_trade_review_templates_incomplete", "quarterly_quality_trends_missing", "behavior_learning_loop_incomplete", "exportable_decision_report_missing"]
        if counts["post_trade_reviews"] == 0:
            blockers.append("post_trade_reviews_missing")
        return self._packet(
            8,
            "journal_review_productization",
            "Journal and review productization",
            "The user needs to learn from behavior, not just archive trades.",
            "Review should convert decisions into rule updates and behavior insights.",
            "Use review templates, trend charts, task boards, and exportable decision reports.",
            50,
            blockers,
            ["Trade journal, post-trade review, monthly decision review, review action plan, and review tasks exist."],
            ["Add richer single-trade review templates.", "Add planned-vs-impulsive attribution and quarterly trend views.", "Add exportable investment decision reports."],
            counts,
        )

    def _notifications_calendar(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["external_notification_channels_missing", "calendar_sync_missing", "event_reminder_feeds_missing", "unhandled_item_escalation_missing"]
        return self._packet(
            9,
            "notifications_calendar",
            "Notifications and calendar",
            "The user should not need to remember every thesis checkpoint or catalyst manually.",
            "Notifications are generated from workflow obligations, not random alerts.",
            "Use a calendar-backed reminder center with channel preferences and escalation status.",
            25,
            blockers,
            ["Local reminders and scheduled-job metadata exist."],
            ["Add email, push, Telegram, Feishu, or another first notification channel.", "Add calendar sync and catalyst feeds.", "Escalate overdue thesis checkpoints and unhandled blockers."],
            counts,
        )

    def _user_system(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["registration_login_missing", "multi_device_sessions_missing", "team_workspace_missing"]
        if counts["privacy_exports"] == 0:
            blockers.append("privacy_export_not_exercised")
        if counts["users"] <= 1:
            blockers.append("role_depth_missing")
        if targets.get("auth", 0) == 0:
            blockers.append("auth_target_missing")
        return self._packet(
            10,
            "complete_user_system",
            "Complete user system",
            "The user must feel their financial memory is private, portable, and permissioned.",
            "Identity, role, session, and privacy controls are product primitives.",
            "Make account, role, session, audit export, data export/delete understandable from Settings.",
            30,
            blockers,
            ["UserAccount, beta access, permission checks, audit surfaces, and an audited privacy export/delete workflow exist."],
            ["Add real registration/login and multi-device sessions.", "Add team workspace roles: owner, approver, observer, admin.", "Exercise the privacy export from Settings before inviting users."],
            {**counts, **targets},
        )

    def _commercialization(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["billing_missing", "plan_limits_missing", "usage_metering_missing", "paid_feature_gates_missing"]
        if counts["support_tasks"] == 0:
            blockers.append("customer_support_flow_not_exercised")
        return self._packet(
            11,
            "commercialization_foundation",
            "Commercialization foundation",
            "The user and buyer need to understand what is included, what is paid, and why value compounds.",
            "Monetization should follow usage and trust, not interrupt the core workflow.",
            "Expose plan status, limits, trial, referral, invoice, and support without cluttering the terminal.",
            15,
            blockers,
            ["Financing readiness tracks pricing and GTM targets, but no billing system exists."],
            ["Add billing provider integration and plan limits.", "Add usage metering for data sync, reports, evals, and workspaces.", "Add invoice/receipt and support console."],
            {**counts, **targets},
        )

    def _product_ops_admin(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["admin_dashboard_missing", "invite_code_management_missing", "feature_flags_missing", "release_note_workflow_missing"]
        if counts["support_tasks"] == 0:
            blockers.append("feedback_inbox_not_exercised")
        return self._packet(
            12,
            "product_ops_admin",
            "Product operations admin",
            "The operator needs to run beta without editing the database or reading logs all day.",
            "Admin surfaces should manage access, feedback, rollout, and support safely.",
            "Create a quiet admin console for users, invites, funnel, flags, feedback, bugs, and release notes.",
            20,
            blockers,
            ["Beta users, operational events, invitation packet, and product stability packet exist."],
            ["Add beta user management and invite codes.", "Add feedback inbox, bug report, and release-note workflow.", "Add feature flags and activation funnel dashboard."],
            {**counts, **targets},
        )

    def _security_engineering(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["threat_model_missing", "dependency_scanning_missing", "secret_scanning_missing", "sast_dast_missing", "rate_limit_missing", "incident_response_incomplete"]
        return self._packet(
            13,
            "security_engineering",
            "Security engineering",
            "The user is trusting the product with sensitive financial context, even before trading keys exist.",
            "Security should reduce blast radius before adding more integrations.",
            "Surface security posture as controls, evidence, incidents, and retention status.",
            25,
            blockers,
            ["Secret references, operational events, audit logs, and safety docs exist."],
            ["Add threat model and least-privilege service account map.", "Add dependency/secret scanning and SAST/DAST in CI.", "Add rate limits, session hardening, audit retention, and incident response drills."],
            {**counts, **targets},
        )

    def _ai_safety(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["prompt_injection_tests_missing", "tool_permission_isolation_incomplete", "model_output_validation_incomplete", "eval_dashboard_missing"]
        return self._packet(
            14,
            "ai_safety",
            "AI safety",
            "The user should get help without accidentally giving the AI agency over money or secrets.",
            "AI can explain and propose; deterministic gates decide whether anything proceeds.",
            "Show AI limitations, evidence, eval failures, and blocked tool attempts transparently.",
            35,
            blockers,
            ["Mock provider, provider-status endpoint, command-bar auditing, and no-direct-execution rules exist."],
            ["Add prompt-injection and sensitive-data redaction evals.", "Enforce tool permission isolation and output validation.", "Add overreliance/excessive-agency warnings and an eval dashboard."],
            counts,
        )

    def _ai_governance(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["model_registry_missing", "prompt_registry_missing", "eval_versioning_missing", "ai_output_provenance_incomplete", "model_disable_switch_missing"]
        return self._packet(
            15,
            "ai_governance",
            "AI governance",
            "The user and investor need to know which model said what, using which prompt and evidence.",
            "AI outputs are versioned artifacts with provenance and human-review policy.",
            "Add a governance dashboard for model, prompt, eval, provenance, review status, and disable controls.",
            30,
            blockers,
            ["AI provider status, research reports, and audit logs exist."],
            ["Add model registry, prompt registry, and eval versioning.", "Persist AI output provenance and human review policy.", "Add model disable switch and AI risk dashboard."],
            {**counts, **targets},
        )

    def _deployment_operability(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["staging_production_separation_missing", "managed_db_redis_missing", "migration_rollback_missing", "slo_sla_error_budget_missing", "log_tracing_cost_monitoring_missing"]
        return self._packet(
            16,
            "deployment_operability",
            "Deployment and operability",
            "The user needs the terminal to be boringly reliable when market stress is high.",
            "Operational readiness is measured by recovery, observability, and controlled rollout.",
            "Show environment, release, health, SLO, logs, tracing, cost, and restore status in ops panels.",
            25,
            blockers,
            ["Docker compose, CI, ops stability report, production targets, and restore-drill plan exist."],
            ["Separate staging and production configs.", "Add managed DB/Redis and migration rollback plan.", "Add blue-green/canary, SLO/SLA, logs, tracing, and cost monitoring."],
            {**counts, **targets},
        )

    def _testing_system(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["frontend_e2e_main_paths_incomplete", "visual_regression_missing", "api_contract_tests_missing", "load_tests_missing", "recovery_drill_tests_missing"]
        return self._packet(
            17,
            "testing_system",
            "Testing system",
            "The user should not discover broken workflows during a trade decision or review.",
            "Tests must cover the workflow story, not only isolated endpoints.",
            "Expose test health by user journey: onboarding, data sync, thesis, gates, paper fill, review, ops.",
            45,
            blockers,
            ["Backend suite, migration smoke, frontend typecheck, demo smoke, and one frontend smoke path exist."],
            ["Add E2E coverage for all main paths and mobile viewports.", "Add visual regression and API contract tests.", "Add adapter contract, load, and recovery-drill tests."],
            {**counts, **targets},
        )

    def _frontend_experience(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["beginner_expert_modes_missing", "keyboard_shortcuts_missing", "saved_table_views_missing", "accessibility_keyboard_nav_incomplete", "mobile_review_flow_incomplete"]
        return self._packet(
            18,
            "frontend_experience",
            "Frontend experience optimization",
            "The user should feel guided when new and fast when advanced.",
            "The UI should progressively disclose complexity while keeping the daily loop one click away.",
            "Add beginner/expert modes, command integrations, saved views, drilldowns, mobile review, and keyboard navigation.",
            55,
            blockers,
            ["Core terminal workspaces, financing readiness, and many product packets are visible."],
            ["Add information-density modes and shortcuts.", "Add saved filters/sorts/table views and better empty/error states.", "Improve accessibility, drawer drilldowns, and mobile review flow."],
            {**counts, **targets},
        )

    def _open_ecosystem(self, counts: dict[str, int], targets: dict[str, int]) -> dict[str, Any]:
        blockers = ["mcp_server_not_production_ready", "sidecar_process_registry_missing", "module_certification_missing", "plugin_sandbox_missing", "marketplace_missing"]
        return self._packet(
            19,
            "open_ecosystem",
            "Open ecosystem",
            "Advanced users should extend research and strategy without bypassing safety controls.",
            "Extensions are typed, permissioned, certified, and audited sidecars.",
            "Show module health, permissions, contract reports, certification status, and install boundaries.",
            30,
            blockers,
            ["Module registry, sidecar policy evaluation, and sidecar contract report safe slices exist."],
            ["Make MCP server production usable.", "Add sidecar process registry and typed adapter contracts.", "Add plugin sandbox, module certification, and permission review."],
            {**counts, **targets},
        )

    def _execution_stack(self, counts: dict[str, int]) -> dict[str, Any]:
        blockers = ["broker_sandbox_adapter_missing", "execution_order_state_machine_incomplete", "idempotency_cancel_replace_missing", "market_hours_and_outage_handling_missing", "post_execution_reconciliation_incomplete"]
        return self._packet(
            20,
            "pre_live_execution_stack",
            "Execution stack before real live trading",
            "The user should never wonder whether an order was submitted, filled, rejected, canceled, or reconciled.",
            "Execution is a state machine with idempotency, reconciliation, rollback, and human approval.",
            "Keep this panel last, red-gated, and explicit about sandbox versus production execution.",
            30,
            blockers,
            ["Prepare, sandbox-run, broker reconciliation plan, kill switch, and small-pilot packets exist."],
            ["Add broker sandbox adapter and explicit account allowlist.", "Add order state machine with idempotency, cancel/replace, partial fill, reject/expire/halt, and market hours.", "Add broker outage handling and post-execution reconciliation before any pilot."],
            counts,
        )

    def _packet(
        self,
        item_no: int,
        key: str,
        title: str,
        user_problem: str,
        logic_principle: str,
        ui_principle: str,
        progress_pct: int,
        blockers: list[str],
        completed: list[str],
        next_actions: list[str],
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "item_no": item_no,
            "key": key,
            "title": title,
            "development_status": "developed_safe_slice",
            "product_status": "blocked" if blockers else "ready",
            "progress_pct": progress_pct,
            "user_problem": user_problem,
            "logic_principle": logic_principle,
            "ui_principle": ui_principle,
            "completed_in_this_pass": completed,
            "blockers": blockers,
            "next_actions": next_actions,
            "optimizations": [
                "Make the next action obvious.",
                "Prefer evidence and workflow state over generic text.",
                "Keep advanced controls available but not in the way of first use.",
            ],
            "metrics": metrics,
            "execution_available": False,
            "capability_kind": "preflight_capability",
            "production_capability": False,
            "capability_boundary": "This packet is preflight readiness for development planning, not a real production capability.",
            "real_broker_call_allowed": False,
            "wallet_signing_available": False,
            "cex_trading_available": False,
        }

    def _counts(self, user_id: str) -> dict[str, int]:
        return {
            "users": self._count(UserAccount),
            "watchlist_items": self._count(WatchlistItem, WatchlistItem.user_id == user_id),
            "reminders": self._count(Reminder, Reminder.user_id == user_id),
            "scheduled_jobs": self._count(ScheduledJob),
            "ledger_entries": self._count(InvestmentLedgerEntry, InvestmentLedgerEntry.user_id == user_id),
            "reconciliation_runs": self._count(ReconciliationRun, ReconciliationRun.user_id == user_id),
            "catalog_entries": self._count(DataCatalogEntry),
            "quality_reports": self._count(DataQualityReport),
            "data_source_connections": self._count(DataSourceConnection),
            "research_reports": self._count(ResearchReport),
            "theses": self._count(InvestmentThesis, InvestmentThesis.user_id == user_id),
            "backtest_runs": self._count(BacktestRun),
            "strategy_rules": self._count(StrategyRule),
            "decision_gates": self._count(DecisionGate),
            "order_drafts": self._count(OrderDraft),
            "post_trade_reviews": self._count(PostTradeReview),
            "workflow_review_tasks": self._count(WorkflowReviewTask, WorkflowReviewTask.user_id == user_id),
            "audit_logs": self._count(AuditLog),
            "operational_events": self._count(OperationalEvent),
            "secret_references": self._count(SecretReference, SecretReference.user_id == user_id),
            "export_artifacts": self._count(ExportArtifact, ExportArtifact.user_id == user_id),
            "privacy_exports": self._count(ExportArtifact, ExportArtifact.user_id == user_id, ExportArtifact.export_type == "user_data_portability_export"),
            "support_tickets": self._count(OperationalEvent, OperationalEvent.user_id == user_id, OperationalEvent.event_type == "support.ticket"),
            "support_tasks": self._count(WorkflowReviewTask, WorkflowReviewTask.user_id == user_id, WorkflowReviewTask.item_type == "beta_support"),
        }

    def _target_counts(self, user_id: str) -> dict[str, int]:
        try:
            rows = self.db.execute(
                select(ProductionReadinessTarget.target_type, func.count())
                .where(ProductionReadinessTarget.user_id == user_id)
                .group_by(ProductionReadinessTarget.target_type)
            ).all()
        except SQLAlchemyError:
            self.db.rollback()
            self.schema_warnings.append(ProductionReadinessTarget.__tablename__)
            return {}
        return {str(key): int(count) for key, count in rows}

    def _count(self, model: Any, *conditions: Any) -> int:
        statement = select(func.count()).select_from(model)
        for condition in conditions:
            statement = statement.where(condition)
        try:
            return int(self.db.scalar(statement) or 0)
        except SQLAlchemyError:
            self.db.rollback()
            self.schema_warnings.append(str(getattr(model, "__tablename__", model.__name__)))
            return 0
