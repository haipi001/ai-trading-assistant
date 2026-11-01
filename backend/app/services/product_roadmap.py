from __future__ import annotations

from typing import Any


PHASES: list[dict[str, Any]] = [
    {
        "phase_no": 1,
        "key": "founder_daily_use_alpha",
        "title": "Founder Daily-Use Alpha",
        "status": "in_progress",
        "goal": "Make the first screen useful every day for the founder before adding broader product surface.",
        "scope": ["onboarding", "today queue", "daily open/close", "core drilldown"],
        "acceptance_criteria": [
            "A new user can complete onboarding and land in the today action queue.",
            "Daily open and close flows create auditable records.",
            "Every queue item drills down to evidence, risk, thesis, or draft context.",
        ],
        "current_progress_pct": 50,
        "next_actions": [
            "Instrument onboarding completion and first meaningful action.",
            "Promote the today action queue as the default workspace entry.",
            "Add daily close review state and open/close history.",
        ],
    },
    {
        "phase_no": 2,
        "key": "real_readonly_data_proof",
        "title": "Real Read-Only Data Proof",
        "status": "started",
        "goal": "Prove one real authenticated read-only adapter end to end before expanding providers.",
        "scope": ["authenticated read-only adapter", "credential reference", "health/preflight", "account snapshot"],
        "acceptance_criteria": [
            "Credentials are referenced, never stored inline.",
            "A signed read-only account snapshot can be synced and audited.",
            "Execution, order routing, withdrawal, and signing flags remain false.",
        ],
        "current_progress_pct": 35,
        "next_actions": [
            "Run Binance Spot read-only adapter against a real read-only key in a private environment.",
            "Add scheduled read-only refresh after manual verification.",
            "Add second provider only after mapping and warnings are stable.",
        ],
    },
    {
        "phase_no": 3,
        "key": "trusted_ledger_data_promotion",
        "title": "Trusted Ledger And Data Promotion",
        "status": "planned",
        "goal": "Move imported statements and snapshots through reconciliation before any decision use.",
        "scope": ["statement import", "reconciliation", "data promotion", "repair workflow"],
        "acceptance_criteria": [
            "Every promoted dataset has source, snapshot, quality report, and reconciliation evidence.",
            "Mismatch repair has an owner, due date, and audit trail.",
            "Unreconciled data is review-only and cannot unlock approval gates.",
        ],
        "current_progress_pct": 30,
        "next_actions": [
            "Add normalized transaction records from statement imports.",
            "Add reconciliation mismatch repair tasks.",
            "Define promotion states from raw to trusted.",
        ],
    },
    {
        "phase_no": 4,
        "key": "research_evidence_thesis_delta",
        "title": "Research Evidence And Thesis Delta",
        "goal": "Make research explain what changed versus the active thesis, with evals and evidence packs.",
        "scope": ["safe LLM access", "evidence packet", "thesis delta", "eval"],
        "acceptance_criteria": [
            "External LLM calls are opt-in and secrets are referenced.",
            "Every report cites snapshots and evidence.",
            "Thesis delta is evaluated before it can change review priority.",
        ],
        "status": "in_progress",
        "current_progress_pct": 32,
        "next_actions": [
            "Human-label the first real-provider eval batch to fill hallucination_rate.",
            "Build evidence packet drilldowns.",
            "Compare new research against active thesis checkpoints.",
        ],
    },
    {
        "phase_no": 5,
        "key": "portfolio_risk_terminal",
        "title": "Portfolio Risk Terminal",
        "status": "planned",
        "goal": "Turn holdings into an inspectable risk terminal before any execution expansion.",
        "scope": ["portfolio risk", "exposure", "correlation", "stress test"],
        "acceptance_criteria": [
            "Exposure is visible by asset, account, factor, currency, and venue.",
            "Stress tests show assumptions, inputs, and stale-data blockers.",
            "Risk terminal links back to thesis and ledger evidence.",
        ],
        "current_progress_pct": 25,
        "next_actions": [
            "Add exposure dimensions and concentration drilldowns.",
            "Add deterministic stress scenarios.",
            "Connect high-risk exposures to today queue actions.",
        ],
    },
    {
        "phase_no": 6,
        "key": "private_beta_foundation",
        "title": "Private Beta Foundation",
        "status": "planned",
        "goal": "Make the product operable for a small private beta without increasing execution risk.",
        "scope": ["auth", "RBAC", "secrets", "monitoring", "backups", "admin"],
        "acceptance_criteria": [
            "Auth and RBAC are mandatory outside local development.",
            "Secrets, monitoring, restore drills, and backups are configured.",
            "Admin surfaces can inspect users, events, errors, and data freshness.",
        ],
        "current_progress_pct": 35,
        "next_actions": [
            "Replace header-only local auth with production auth.",
            "Add admin console for users, events, jobs, and backups.",
            "Run restore drill and monitoring smoke tests before invites.",
        ],
    },
    {
        "phase_no": 7,
        "key": "traction_commercial_loop",
        "title": "Traction And Commercial Loop",
        "status": "planned",
        "goal": "Create the waitlist, analytics, pricing, demo, and data room loop for commercial proof.",
        "scope": ["waitlist", "analytics", "pricing", "demo", "data room"],
        "acceptance_criteria": [
            "Waitlist and activation analytics are instrumented.",
            "Pricing hypothesis and usage limits are visible.",
            "Demo path and data room export are repeatable.",
        ],
        "current_progress_pct": 20,
        "next_actions": [
            "Add waitlist capture and invite status.",
            "Add analytics for onboarding, daily queue, and retention.",
            "Build repeatable demo/data room export.",
        ],
    },
    {
        "phase_no": 8,
        "key": "broker_sandbox_execution_proof",
        "title": "Broker Sandbox Execution Proof",
        "status": "locked",
        "goal": "Prove sandbox-only execution adapter behavior with a full audit and reconciliation loop.",
        "scope": ["sandbox adapter", "order state machine", "audit", "reconciliation"],
        "acceptance_criteria": [
            "Sandbox execution cannot reach production credentials or live accounts.",
            "Every sandbox order has idempotency, state transitions, and reconciliation.",
            "Kill switch and rollback are tested before any pilot discussion.",
        ],
        "current_progress_pct": 15,
        "next_actions": [
            "Define sandbox adapter contract.",
            "Add order state machine and reconciliation audit.",
            "Keep production execution disabled.",
        ],
    },
    {
        "phase_no": 9,
        "key": "controlled_pilot",
        "title": "Controlled Pilot",
        "status": "locked",
        "goal": "Only consider a tiny allowlisted pilot after legal, ops, and whitelist gates pass.",
        "scope": ["legal", "operations", "allowlist", "small pilot"],
        "acceptance_criteria": [
            "Legal and operational approval are recorded.",
            "Allowlist, limits, monitoring, and rollback are active.",
            "Pilot remains small, reversible, and explicitly approved by humans.",
        ],
        "current_progress_pct": 0,
        "next_actions": [
            "Do not start until phases 1-8 have passing evidence.",
            "Prepare legal and operational gate checklist.",
            "Define hard stop conditions before any pilot.",
        ],
    },
]


class ProductRoadmapService:
    def phases(self) -> list[dict[str, Any]]:
        return [self._phase_payload(phase) for phase in PHASES]

    def phase(self, phase_no: int) -> dict[str, Any]:
        for phase in self.phases():
            if phase["phase_no"] == phase_no:
                return phase
        raise ValueError("product roadmap phase not found")

    def summary(self) -> dict[str, Any]:
        phases = self.phases()
        blockers = [phase["title"] for phase in phases if phase["status"] in {"locked", "planned"}]
        return {
            "status": "preflight_roadmap",
            "capability_kind": "product_development_roadmap",
            "production_capability": False,
            "execution_available": False,
            "phases_total": len(phases),
            "current_phase": phases[0],
            "next_phase": phases[1],
            "average_progress_pct": round(sum(phase["current_progress_pct"] for phase in phases) / len(phases)),
            "locked_phases": sum(1 for phase in phases if phase["status"] == "locked"),
            "blockers": blockers[:8],
            "next_actions": phases[0]["next_actions"] + phases[1]["next_actions"][:1],
            "phases": phases,
        }

    def _phase_payload(self, phase: dict[str, Any]) -> dict[str, Any]:
        return {
            **phase,
            "capability_kind": "development_phase",
            "production_capability": False,
            "execution_available": False,
            "real_broker_call_allowed": False,
            "live_execution_available": False,
        }
