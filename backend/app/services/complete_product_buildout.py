from __future__ import annotations

from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from app.services.complete_product_readiness import CompleteProductReadinessService


class CompleteProductBuildoutService:
    """Product-completion plan that is executable, gated, and safe by default."""

    def __init__(self, db: Session):
        self.db = db

    def summary(self, *, user_id: str = "default-user") -> dict[str, Any]:
        readiness = CompleteProductReadinessService(self.db).summary(user_id=user_id)
        projects = self.projects(user_id=user_id)
        launch = self.launch_preparation(user_id=user_id)
        private_core = self.private_core(user_id=user_id)
        restricted = self.safety_limited_capabilities(user_id=user_id)
        progress = round(mean([item["progress_pct"] for item in projects]))
        critical_blockers = [
            blocker
            for item in projects
            for blocker in item["blockers"][:2]
        ][:18]
        return {
            "status": "developed_safe_slice",
            "product_stage": "pre_private_beta",
            "target": "complete_product_buildout_to_private_beta_then_public_launch",
            "readiness_progress_pct": readiness["progress_pct"],
            "buildout_progress_pct": progress,
            "launch_status": launch["launch_status"],
            "private_core_policy_status": private_core["policy_status"],
            "safety_boundary_status": restricted["boundary_status"],
            "next_release_gate": "founder_daily_use_alpha",
            "projects_total": len(projects),
            "projects_ready": len([item for item in projects if item["status"] == "ready"]),
            "projects_blocked": len([item for item in projects if item["status"] != "ready"]),
            "execution_available": False,
            "real_broker_call_allowed": False,
            "wallet_signing_available": False,
            "cex_trading_available": False,
            "critical_blockers": critical_blockers,
            "release_stages": self.release_stages(),
            "projects": projects,
            "launch_preparation": launch,
            "private_core": private_core,
            "safety_limited_capabilities": restricted,
        }

    def projects(self, *, user_id: str = "default-user") -> list[dict[str, Any]]:
        readiness_items = {item["key"]: item for item in CompleteProductReadinessService(self.db).items(user_id=user_id)}
        return [
            self._project(
                1,
                "onboarding_daily_loop",
                "Real onboarding, open/close workflow, and today queue",
                readiness_items["daily_use_loop"]["progress_pct"],
                readiness_items["daily_use_loop"]["blockers"],
                "The user lands in one daily path: connect data, inspect exceptions, update thesis, decide, review.",
                "founder_daily_use_alpha",
                [
                    "First-run profile, risk boundary, and account-intent wizard.",
                    "Open checklist, close checklist, today queue, and abnormal-state next actions.",
                    "Auto-created review reminders and thesis checkpoints.",
                ],
                [
                    "A first-time user reaches the today queue without reading docs.",
                    "Every queue item has one next action and a blocking reason.",
                    "No execution action is exposed from onboarding.",
                ],
            ),
            self._project(
                2,
                "authenticated_readonly_adapter",
                "First real authenticated read-only broker or CEX adapter",
                35,
                ["real_provider_credentials_flow_missing", "adapter_contract_certification_missing", "secret_rotation_proof_missing"],
                "The user sees real holdings without giving the system trading authority.",
                "private_beta_data_proof",
                [
                    "Secret-reference-only credentials; no inline secrets.",
                    "Read-only account, balances, positions, orders, and statement snapshot import.",
                    "Adapter contract tests and provider permission proof.",
                ],
                [
                    "One real account syncs with read-only permissions.",
                    "Trading, withdrawal, transfer, and wallet-sign permissions are rejected at setup.",
                    "Adapter produces data catalog entry, quality report, and audit log.",
                ],
            ),
            self._project(
                3,
                "ledger_repair_workflow",
                "Ledger repair and reconciliation workflow",
                readiness_items["complete_investment_ledger"]["progress_pct"],
                readiness_items["complete_investment_ledger"]["blockers"],
                "The user can fix statement differences without editing raw rows or trusting guesses.",
                "trusted_portfolio_memory",
                [
                    "Multi-currency cash, FX, fees, interest, dividends, splits, airdrops, and transfers.",
                    "Reconciliation break assignment, repair suggestions, manual acceptance, and audit.",
                    "Tax-lot and cost-basis repair with before/after preview.",
                ],
                [
                    "A blocking break can be triaged, repaired, re-run, and exported.",
                    "Every repair has actor, reason, source evidence, and rollback path.",
                    "Order approval remains locked by gates, not by ledger repair alone.",
                ],
            ),
            self._project(
                4,
                "dataset_version_replay",
                "Dataset versioning, snapshot replay, and data promotion",
                readiness_items["deep_data_trust"]["progress_pct"],
                readiness_items["deep_data_trust"]["blockers"],
                "The user can reproduce why a decision was made from the exact data state used then.",
                "audit_replay_ready",
                [
                    "Raw payload hash, immutable dataset version, and snapshot replay.",
                    "Provider fallback, rate-limit handling, entitlement checks, and stale/delayed/realtime tags.",
                    "Promotion rule from raw data to review-safe and decision-safe datasets.",
                ],
                [
                    "A historical order draft can replay its data snapshot.",
                    "Stale, delayed, entitlement-blocked, and fallback data remain visible downstream.",
                    "No dataset is decision-safe without promotion evidence.",
                ],
            ),
            self._project(
                5,
                "research_event_terminal",
                "Research event feeds, catalyst calendar, and evidence packets",
                readiness_items["research_terminal_depth"]["progress_pct"],
                readiness_items["research_terminal_depth"]["blockers"],
                "The user sees what changed against their thesis, not generic market noise.",
                "thesis_delta_ready",
                [
                    "News, filings, earnings, macro, governance, unlock, and on-chain events.",
                    "Thesis delta detection, position-related summaries, and catalyst calendar.",
                    "Evidence packet linked to memo, thesis update, and order draft rationale.",
                ],
                [
                    "A thesis update cites multiple source records.",
                    "A catalyst creates a dated review task.",
                    "AI output is evidence-bound and cannot create orders.",
                ],
            ),
            self._project(
                6,
                "portfolio_risk_terminal",
                "Portfolio allocation, exposure, and stress-risk terminal",
                readiness_items["portfolio_management_depth"]["progress_pct"],
                readiness_items["portfolio_management_depth"]["blockers"],
                "The user understands concentration, liquidity, counterparty, and drawdown risk before deciding.",
                "portfolio_risk_review_ready",
                [
                    "Allocation, sector, theme, factor, correlation, concentration, and liquidity views.",
                    "Counterparty, exchange, stablecoin, DeFi, and wallet exposure summaries.",
                    "Scenario stress tests and risk-budget consumption.",
                ],
                [
                    "Every holding maps to at least one exposure bucket.",
                    "Stress output is shown beside thesis and gate checks.",
                    "Risk budget breaches create review tasks.",
                ],
            ),
            self._project(
                7,
                "notifications_calendar",
                "Notifications, calendar, and escalation",
                readiness_items["notifications_calendar"]["progress_pct"],
                readiness_items["notifications_calendar"]["blockers"],
                "The user does not manually remember every thesis checkpoint or catalyst.",
                "retention_loop_ready",
                [
                    "Email or one chat channel first; push/SMS/Telegram/Feishu later.",
                    "Calendar sync for earnings, unlocks, governance votes, macro events, and thesis checkpoints.",
                    "Overdue item escalation and notification preferences.",
                ],
                [
                    "A thesis checkpoint appears on the calendar and in today queue.",
                    "Missed high-priority items escalate according to preference.",
                    "External notifications are opt-in and auditable.",
                ],
            ),
            self._project(
                8,
                "auth_rbac_privacy",
                "Production auth, RBAC, sessions, and privacy controls",
                readiness_items["complete_user_system"]["progress_pct"],
                readiness_items["complete_user_system"]["blockers"],
                "The user can trust identity, roles, sessions, export/delete, and privacy settings.",
                "private_beta_security_gate",
                [
                    "Registration/login, session management, MFA-ready hooks, and device visibility.",
                    "Owner, approver, observer, admin roles with permission tests.",
                    "Audit export, user data export/delete, and privacy settings.",
                ],
                [
                    "Every sensitive route has permission coverage.",
                    "Session revocation works across devices.",
                    "Data export/delete is documented and audited.",
                ],
            ),
            self._project(
                9,
                "billing_admin_ops",
                "Billing, plan limits, support, beta admin, and release ops",
                min(readiness_items["commercialization_foundation"]["progress_pct"], readiness_items["product_ops_admin"]["progress_pct"]),
                readiness_items["commercialization_foundation"]["blockers"] + readiness_items["product_ops_admin"]["blockers"],
                "The product can run a beta, learn from users, and charge without manual database work.",
                "paid_beta_ready",
                [
                    "Billing sandbox, plan limits, trial/invite/referral, usage metering, invoices, and receipts.",
                    "Beta user admin, feature flags, feedback inbox, bug report, and release notes.",
                    "Activation, retention, churn, and paid-intent analytics.",
                ],
                [
                    "A beta invite can be issued, activated, limited, and supported.",
                    "Paid feature gates are deterministic and auditable.",
                    "No billing provider secret appears in logs or metadata.",
                ],
            ),
            self._project(
                10,
                "security_ai_governance",
                "Security engineering, AI safety, and AI governance",
                min(
                    readiness_items["security_engineering"]["progress_pct"],
                    readiness_items["ai_safety"]["progress_pct"],
                    readiness_items["ai_governance"]["progress_pct"],
                ),
                readiness_items["security_engineering"]["blockers"] + readiness_items["ai_safety"]["blockers"] + readiness_items["ai_governance"]["blockers"],
                "The user gets AI help without giving it hidden authority over money, secrets, or decisions.",
                "security_governance_gate",
                [
                    "Threat model, dependency/secret scanning, SAST/DAST, rate limits, incident response.",
                    "Prompt-injection, redaction, tool isolation, output validation, overreliance and agency warnings.",
                    "Model registry, prompt registry, eval versioning, provenance, disable switch, AI risk dashboard.",
                ],
                [
                    "AI cannot call trading, wallet, transfer, or secret-revealing tools.",
                    "Every AI claim in decision workflows has evidence or is marked unsupported.",
                    "Security scans and evals are release gates.",
                ],
            ),
            self._project(
                11,
                "test_release_recovery",
                "E2E, visual, load, recovery, and release testing",
                readiness_items["testing_system"]["progress_pct"],
                readiness_items["testing_system"]["blockers"],
                "The user should not discover broken paths during market stress.",
                "release_candidate_gate",
                [
                    "Frontend E2E across onboarding, data sync, thesis, gates, paper fill, review, and ops.",
                    "Mobile viewport, visual regression, API contracts, migration rollback, adapter mocks, load tests.",
                    "Backup/restore and incident recovery drills.",
                ],
                [
                    "The 7-minute investor demo and daily-use loop are protected by E2E.",
                    "Rollback and restore drills are executed in staging.",
                    "Release cannot proceed when critical paths fail.",
                ],
            ),
            self._project(
                12,
                "broker_sandbox_execution_stack",
                "Broker sandbox execution stack, still last",
                readiness_items["pre_live_execution_stack"]["progress_pct"],
                readiness_items["pre_live_execution_stack"]["blockers"],
                "The user can prove order lifecycle handling in sandbox without risking production accounts.",
                "sandbox_only_execution_proof",
                [
                    "Broker sandbox adapter, account allowlist, signed approval packet, and order state machine.",
                    "Idempotency, cancel/replace, partial fill, reject/expire/halt, market hours, outage handling.",
                    "Post-execution reconciliation and rollback drill.",
                ],
                [
                    "Sandbox order lifecycle is reconciled end to end.",
                    "Production broker credentials are rejected by sandbox routes.",
                    "Real execution stays disabled until legal, operational, and user-consent gates pass.",
                ],
            ),
        ]

    def launch_preparation(self, *, user_id: str = "default-user") -> dict[str, Any]:
        sections = [
            self._launch_section("environment", "Environment separation", "blocked", "local, staging, production, and sandbox must be isolated.", ["staging_env_missing", "production_env_missing"], "private_beta"),
            self._launch_section("secrets", "Secrets and key management", "blocked", "All provider credentials must be secret references with rotation and audit.", ["managed_secret_store_missing", "rotation_drill_missing"], "private_beta"),
            self._launch_section("auth_rbac", "Auth, RBAC, and sessions", "blocked", "Production auth and roles must protect every financial and admin route.", ["production_auth_missing", "rbac_route_matrix_incomplete"], "private_beta"),
            self._launch_section("data_protection", "Data protection and privacy", "blocked", "Export, deletion, retention, encryption, and privacy settings must be defined.", ["privacy_policy_missing", "data_deletion_workflow_missing"], "private_beta"),
            self._launch_section("observability", "Monitoring, logs, tracing, and SLO", "blocked", "The operator must see uptime, errors, latency, job failures, and cost.", ["external_monitoring_missing", "slo_error_budget_missing"], "private_beta"),
            self._launch_section("backup_restore", "Backup, restore, and migration rollback", "blocked", "A bad deploy or data incident must have rehearsed recovery.", ["staging_restore_drill_missing", "migration_rollback_drill_missing"], "private_beta"),
            self._launch_section("security_review", "Security review and incident response", "blocked", "Threat model, scanning, rate limits, audit retention, and incident playbooks are release gates.", ["threat_model_missing", "incident_response_drill_missing"], "private_beta"),
            self._launch_section("legal_compliance", "Legal and compliance boundary", "blocked", "Terms, privacy, disclaimers, data processing, and non-advisory boundaries need counsel review.", ["counsel_review_missing", "public_compliance_memo_missing"], "public_launch"),
            self._launch_section("support_ops", "Support and customer operations", "blocked", "Support inbox, bug reports, release notes, and escalation path must exist before beta.", ["support_console_missing", "feedback_triage_missing"], "private_beta"),
            self._launch_section("go_to_market", "Pricing, GTM, and onboarding analytics", "blocked", "Plan limits, trial, usage metering, activation, retention, and paid intent must be measured.", ["pricing_gate_missing", "activation_funnel_missing"], "paid_beta"),
            self._launch_section("data_room", "Data room and investor materials", "review_required", "Deck, one-pager, demo video, architecture, legal boundary, security plan, and financial model should be current.", ["data_room_refresh_required"], "fundraising"),
            self._launch_section("release_management", "Release management", "blocked", "Blue-green or canary release, rollback, changelog, and owner approval must be required.", ["canary_release_missing", "release_owner_approval_missing"], "public_launch"),
        ]
        blockers = [blocker for section in sections for blocker in section["blockers"]]
        return {
            "launch_status": "blocked" if blockers else "ready",
            "recommended_launch_order": ["founder_daily_use_alpha", "private_beta", "paid_beta", "public_launch", "sandbox_execution_pilot"],
            "sections": sections,
            "blockers": blockers,
            "execution_available": False,
        }

    def private_core(self, *, user_id: str = "default-user") -> dict[str, Any]:
        proprietary_modules = [
            self._private_module("decision_memory_graph", "Decision memory, thesis graph, and behavior-risk learning", "This is the product's differentiated memory of why the user acts.", ["Public API contracts", "Redacted examples", "Schema docs"]),
            self._private_module("gate_policy_engine", "Gate policies, risk scoring, and override analysis", "This encodes safety, decision quality, and product judgment.", ["Policy interface", "Sample policy fixtures"]),
            self._private_module("data_promotion_engine", "Dataset promotion, entitlements, replay scoring, and provider reliability", "This determines what data can influence decisions.", ["Adapter contract", "Hashing conventions"]),
            self._private_module("research_delta_engine", "Thesis delta detection, evidence ranking, and memo generation", "This is the research workflow moat.", ["Research memo template", "Citation schema"]),
            self._private_module("portfolio_risk_models", "Exposure, liquidity, counterparty, stress, and risk-budget models", "These models shape product quality and liability boundaries.", ["Risk result schema", "Sample stress scenarios"]),
            self._private_module("ai_eval_governance", "Prompt registry, eval sets, provenance, model routing, and disable switch", "This protects AI trust and reduces hallucination/agency risk.", ["Eval result format", "Model card template"]),
            self._private_module("billing_entitlement_admin", "Pricing, entitlements, usage metering, beta ops, and support console", "This is commercial infrastructure and user operations data.", ["Plan capability manifest"]),
            self._private_module("execution_safety_orchestrator", "Sandbox-to-live approval package, kill switch, rollback, and broker reconciliation logic", "This is high-risk safety infrastructure and should not expose bypass paths.", ["Sandbox contract", "Audit event schema"]),
        ]
        open_source_candidates = [
            "UI shell without proprietary scoring rules",
            "typed adapter SDK and mock adapters",
            "sample-data fixtures and demo workflows",
            "documentation, schemas, and non-sensitive runbooks",
            "MCP/tool protocol interfaces without privileged implementations",
            "sandbox examples that cannot submit production orders",
        ]
        return {
            "policy_status": "defined",
            "default_license_strategy": "open_interfaces_private_core",
            "proprietary_modules": proprietary_modules,
            "open_source_candidates": open_source_candidates,
            "rules": [
                "Never open-source secrets, provider keys, customer data, audit logs, or production configs.",
                "Do not publish bypassable execution policies, live broker credentials flow, or kill-switch internals.",
                "Open-source interfaces and sample adapters only after permission and safety review.",
                "Keep model/eval prompts private when they encode compliance, risk, pricing, or anti-abuse logic.",
            ],
            "execution_available": False,
        }

    def safety_limited_capabilities(self, *, user_id: str = "default-user") -> dict[str, Any]:
        allowed = [
            self._capability("read_only_sync", "Authenticated read-only account sync", "allowed_safe", "Credentials are secret references and provider permissions are read-only.", ["trading_permission_detected", "withdrawal_permission_detected"]),
            self._capability("statement_import_repair", "Statement import and ledger repair", "allowed_safe", "Repairs are manual, audited, and reversible.", ["auto_repair_without_review"]),
            self._capability("data_replay", "Dataset versioning and replay", "allowed_safe", "Replay cannot create orders or mutate historical records.", ["mutable_snapshot"]),
            self._capability("research_evidence", "Research events and evidence packets", "allowed_safe", "AI may summarize and cite, but cannot approve or submit orders.", ["uncited_ai_claim", "order_creation_by_ai"]),
            self._capability("portfolio_risk", "Portfolio risk analytics", "allowed_safe", "Risk output creates review tasks, not trades.", ["auto_rebalance_execution"]),
            self._capability("notifications", "Opt-in notifications and calendar reminders", "allowed_safe", "External messages require channel consent and audit.", ["unconsented_external_message"]),
            self._capability("auth_rbac_billing_admin", "Auth, RBAC, billing sandbox, and admin console", "allowed_safe", "Billing starts in sandbox/test mode and never logs secrets.", ["live_billing_without_plan_review"]),
            self._capability("security_ai_governance", "Security scans and AI governance", "allowed_safe", "Scanning and evals are release gates.", ["eval_bypass", "sensitive_data_in_eval_log"]),
            self._capability("e2e_recovery", "E2E, visual, load, and recovery tests", "allowed_safe", "Tests use staging, synthetic data, or redacted beta data.", ["production_data_load_test"]),
            self._capability("broker_sandbox", "Broker sandbox order lifecycle", "sandbox_only", "Only sandbox credentials and allowlisted accounts are accepted.", ["production_broker_credentials", "real_order_submission"]),
        ]
        forbidden = [
            "real_broker_order_submission",
            "cex_spot_or_derivatives_trading",
            "wallet_signing_or_transfer",
            "withdrawal_or_deposit_initiation",
            "dex_swap_or_bridge",
            "autonomous_live_execution",
            "secret_value_storage_in_database",
            "ai_tool_access_to_execution_without_human_approval",
        ]
        return {
            "boundary_status": "enforced",
            "allowed_capabilities": allowed,
            "forbidden_until_explicit_release_gate": forbidden,
            "production_unlock_gates": [
                "qualified legal review",
                "auth/RBAC/session hardening complete",
                "secret manager and key rotation complete",
                "provider sandbox certification complete",
                "E2E, load, restore, rollback, and incident drills pass",
                "user consent and human approval packet recorded",
                "audit retention and kill switch verified",
            ],
            "execution_available": False,
            "real_broker_call_allowed": False,
            "wallet_signing_available": False,
            "cex_trading_available": False,
        }

    def release_stages(self) -> list[dict[str, Any]]:
        return [
            self._stage("founder_daily_use_alpha", "Founder daily-use alpha", "Daily workflow works with sample/read-only data and paper workflows.", ["onboarding_daily_loop"]),
            self._stage("private_beta", "Private beta", "Auth, read-only adapter, monitoring, backup, support, and privacy controls are ready.", ["authenticated_readonly_adapter", "auth_rbac_privacy", "test_release_recovery"]),
            self._stage("paid_beta", "Paid beta", "Billing sandbox, plan limits, retention analytics, and support ops are ready.", ["billing_admin_ops", "notifications_calendar"]),
            self._stage("public_launch", "Public launch", "Legal, security, deployment, incident response, and release management gates pass.", ["security_ai_governance", "test_release_recovery"]),
            self._stage("sandbox_execution_pilot", "Sandbox execution pilot", "Broker sandbox order lifecycle is proven after the product is useful without live execution.", ["broker_sandbox_execution_stack"]),
        ]

    def _project(
        self,
        sequence: int,
        key: str,
        title: str,
        progress_pct: int,
        blockers: list[str],
        user_value: str,
        release_gate: str,
        safe_development_scope: list[str],
        acceptance_criteria: list[str],
    ) -> dict[str, Any]:
        cleaned_blockers = blockers[:8]
        return {
            "sequence": sequence,
            "key": key,
            "title": title,
            "status": "blocked" if cleaned_blockers else "ready",
            "progress_pct": progress_pct,
            "user_value": user_value,
            "release_gate": release_gate,
            "safe_development_scope": safe_development_scope,
            "acceptance_criteria": acceptance_criteria,
            "blockers": cleaned_blockers,
            "blocked_actions": [
                "real_broker_order_submission",
                "cex_trading",
                "wallet_signing",
                "withdrawals_or_transfers",
                "autonomous_live_execution",
            ],
            "execution_available": False,
        }

    def _launch_section(
        self,
        key: str,
        title: str,
        status: str,
        purpose: str,
        blockers: list[str],
        required_before: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "status": status,
            "purpose": purpose,
            "required_before": required_before,
            "blockers": blockers,
            "evidence_required": [
                "owner",
                "runbook_or_policy",
                "test_or_drill_result",
                "audit_event_or_export",
            ],
        }

    def _private_module(
        self,
        key: str,
        title: str,
        reason_to_keep_private: str,
        open_boundary: list[str],
    ) -> dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "reason_to_keep_private": reason_to_keep_private,
            "open_source_boundary": open_boundary,
            "must_not_publish": [
                "customer data",
                "secret values",
                "production configs",
                "live execution bypass details",
            ],
        }

    def _capability(
        self,
        key: str,
        title: str,
        status: str,
        safe_mode: str,
        hard_blocks: list[str],
    ) -> dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "status": status,
            "safe_mode": safe_mode,
            "hard_blocks": hard_blocks,
            "requires_audit": True,
            "execution_available": False,
        }

    def _stage(self, key: str, title: str, exit_criteria: str, required_projects: list[str]) -> dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "exit_criteria": exit_criteria,
            "required_projects": required_projects,
            "execution_available": False,
        }
