from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset
from app.models import BehaviorIntervention
from app.models import DecisionGate
from app.models import InvestmentThesis
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import RiskCheck
from app.models import StrategyPlaybook
from app.models import ThesisCheckpoint
from app.models import WorkflowState


REQUIRED_GATE_TYPES = {"RESEARCH_GATE", "THESIS_GATE", "RISK_GATE", "BEHAVIOR_GATE", "EXECUTION_GATE"}
FRESH_THESIS_CHECKPOINT_DAYS = 14


class StageReadinessService:
    def __init__(self, db: Session):
        self.db = db

    def queue(self, *, user_id: str = "default-user", limit: int = 25) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        intents = self._candidate_intents(user_id=user_id, limit=max(limit, 100))
        items = [self._item_for_intent(intent, generated_at=generated_at) for intent in intents]
        items.sort(key=lambda row: (readiness_rank(row["readiness"]), row["asset_symbol"] or "", row["created_at"]))
        items = items[:limit]
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "total_items": len(items),
            "ready_count": sum(1 for item in items if item["readiness"] == "ready_for_human_review"),
            "review_required_count": sum(1 for item in items if item["readiness"] == "review_required"),
            "blocked_count": sum(1 for item in items if item["readiness"] == "blocked"),
            "execution_available": False,
            "items": items,
        }

    def _candidate_intents(self, *, user_id: str, limit: int) -> list[OrderIntent]:
        intents = list(
            self.db.scalars(
                select(OrderIntent)
                .order_by(OrderIntent.created_at.desc(), OrderIntent.id.desc())
                .limit(limit)
            ).all()
        )
        filtered: list[OrderIntent] = []
        for intent in intents:
            thesis = self.db.get(InvestmentThesis, intent.investment_thesis_id) if intent.investment_thesis_id else None
            playbook = self.db.get(StrategyPlaybook, intent.strategy_playbook_id) if intent.strategy_playbook_id else None
            if thesis is not None and thesis.user_id != user_id:
                continue
            if playbook is not None and playbook.user_id != user_id:
                continue
            filtered.append(intent)
        return filtered

    def _item_for_intent(self, intent: OrderIntent, *, generated_at: datetime) -> dict[str, Any]:
        asset = self.db.get(Asset, intent.asset_id)
        draft = self._latest_draft(intent.id)
        checks = [
            self._strategy_playbook_check(intent),
            self._investment_thesis_check(intent),
            self._thesis_monitor_check(intent, generated_at=generated_at),
            self._decision_gates_check(intent),
            self._risk_engine_check(intent),
            self._behavior_engine_check(intent),
            self._workflow_state_check(intent, draft),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        next_actions = unique_list(action for check in checks for action in check["next_actions"])
        readiness = "ready_for_human_review"
        if any(check["status"] == "block" for check in checks):
            readiness = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            readiness = "review_required"
        return {
            "id": f"stage-5-11:{intent.id}",
            "subject_type": "order_draft" if draft is not None else "order_intent",
            "readiness": readiness,
            "title": self._title(intent, asset, draft),
            "detail": self._detail(readiness, checks),
            "asset_id": intent.asset_id,
            "asset_symbol": asset.symbol if asset else None,
            "order_intent_id": intent.id,
            "order_draft_id": draft.id if draft else None,
            "strategy_playbook_id": intent.strategy_playbook_id,
            "thesis_id": intent.investment_thesis_id,
            "current_workflow_state": checks[-1]["evidence"].get("current_state"),
            "blockers": blockers,
            "next_actions": next_actions,
            "checks": checks,
            "created_at": draft.created_at if draft else intent.created_at,
            "execution_available": False,
        }

    def _strategy_playbook_check(self, intent: OrderIntent) -> dict[str, Any]:
        playbook = self.db.get(StrategyPlaybook, intent.strategy_playbook_id) if intent.strategy_playbook_id else None
        if playbook is None:
            return check(
                5,
                "strategy_playbook",
                "Strategy Playbook",
                "block",
                "Order intent is not linked to an active strategy playbook.",
                blockers=["Missing StrategyPlaybook link before order workflow."],
                next_actions=["Attach an active StrategyPlaybook before creating or reviewing an order draft."],
            )
        if not playbook.is_active:
            return check(
                5,
                "strategy_playbook",
                "Strategy Playbook",
                "block",
                f"Linked playbook {playbook.name} is inactive.",
                blockers=["Linked StrategyPlaybook is inactive."],
                next_actions=["Reactivate the playbook or attach a current strategy playbook."],
                related_entity_type="StrategyPlaybook",
                related_entity_id=playbook.id,
            )
        status = "ok" if playbook.requires_human_approval else "warn"
        return check(
            5,
            "strategy_playbook",
            "Strategy Playbook",
            status,
            f"Linked playbook {playbook.name}; automation level {playbook.automation_level}.",
            blockers=[],
            next_actions=[] if status == "ok" else ["Confirm this playbook still requires human approval before downstream use."],
            related_entity_type="StrategyPlaybook",
            related_entity_id=playbook.id,
            evidence={"automation_level": playbook.automation_level, "requires_human_approval": playbook.requires_human_approval},
        )

    def _investment_thesis_check(self, intent: OrderIntent) -> dict[str, Any]:
        thesis = self.db.get(InvestmentThesis, intent.investment_thesis_id) if intent.investment_thesis_id else None
        explicit_rationale = bool((intent.user_rationale or intent.rationale or "").strip())
        if thesis is None:
            status = "warn" if explicit_rationale else "block"
            return check(
                6,
                "investment_thesis",
                "Investment Thesis",
                status,
                "No linked thesis; explicit rationale exists." if explicit_rationale else "No linked thesis or explicit rationale exists.",
                blockers=[] if explicit_rationale else ["Missing InvestmentThesis or explicit user rationale."],
                next_actions=["Create or attach an active InvestmentThesis before approval or paper execution."],
            )
        if thesis.status not in {"active", "monitoring"}:
            return check(
                6,
                "investment_thesis",
                "Investment Thesis",
                "block",
                f"Linked thesis is {thesis.status}.",
                blockers=[f"InvestmentThesis status is {thesis.status}, not active/monitoring."],
                next_actions=["Update, replace, or close the thesis before relying on this order intent."],
                related_entity_type="InvestmentThesis",
                related_entity_id=thesis.id,
            )
        return check(
            6,
            "investment_thesis",
            "Investment Thesis",
            "ok",
            "Linked thesis is active or monitoring.",
            related_entity_type="InvestmentThesis",
            related_entity_id=thesis.id,
            evidence={"status": thesis.status, "confidence": float(thesis.confidence)},
        )

    def _thesis_monitor_check(self, intent: OrderIntent, *, generated_at: datetime) -> dict[str, Any]:
        thesis = self.db.get(InvestmentThesis, intent.investment_thesis_id) if intent.investment_thesis_id else None
        if thesis is None:
            return check(
                7,
                "thesis_monitor",
                "Thesis Capture + Monitor",
                "block",
                "Cannot monitor thesis freshness without a linked thesis.",
                blockers=["Missing linked thesis monitor target."],
                next_actions=["Attach a thesis and record a checkpoint with current facts."],
            )
        latest = self._latest_checkpoint(thesis.id)
        if latest is None:
            return check(
                7,
                "thesis_monitor",
                "Thesis Capture + Monitor",
                "warn",
                "No thesis checkpoint has been recorded.",
                next_actions=["Record a thesis monitor checkpoint before relying on this intent."],
                related_entity_type="InvestmentThesis",
                related_entity_id=thesis.id,
            )
        if latest.invalidates_thesis:
            return check(
                7,
                "thesis_monitor",
                "Thesis Capture + Monitor",
                "block",
                "Latest checkpoint invalidates the thesis.",
                blockers=["Latest ThesisCheckpoint invalidates the linked thesis."],
                next_actions=["Close or rewrite the thesis before any order review."],
                related_entity_type="ThesisCheckpoint",
                related_entity_id=latest.id,
            )
        age_days = (generated_at - normalize_dt(latest.created_at)).days
        if age_days > FRESH_THESIS_CHECKPOINT_DAYS:
            return check(
                7,
                "thesis_monitor",
                "Thesis Capture + Monitor",
                "warn",
                f"Latest checkpoint is {age_days} days old.",
                next_actions=["Refresh the thesis checkpoint with current structured facts."],
                related_entity_type="ThesisCheckpoint",
                related_entity_id=latest.id,
                evidence={"age_days": age_days, "weakens_thesis": latest.weakens_thesis},
            )
        status = "warn" if latest.weakens_thesis else "ok"
        return check(
            7,
            "thesis_monitor",
            "Thesis Capture + Monitor",
            status,
            "Latest checkpoint weakens the thesis." if latest.weakens_thesis else "Latest checkpoint is fresh and does not invalidate the thesis.",
            next_actions=["Require explicit review of weakened thesis evidence."] if latest.weakens_thesis else [],
            related_entity_type="ThesisCheckpoint",
            related_entity_id=latest.id,
            evidence={"age_days": age_days, "supports_thesis": latest.supports_thesis, "weakens_thesis": latest.weakens_thesis},
        )

    def _decision_gates_check(self, intent: OrderIntent) -> dict[str, Any]:
        latest = self._latest_gates(intent.id)
        missing = sorted(REQUIRED_GATE_TYPES - set(latest))
        blocked = [gate_type for gate_type, gate in latest.items() if gate.status == "BLOCKED"]
        warnings = [gate_type for gate_type, gate in latest.items() if gate.status in {"WARNING", "HARD_CONFIRM_REQUIRED"}]
        if missing or blocked:
            return check(
                8,
                "decision_gates",
                "Decision Gates",
                "block",
                f"Missing gates: {', '.join(missing) or 'none'}; blocked gates: {', '.join(blocked) or 'none'}.",
                blockers=[f"Missing gate {gate}" for gate in missing] + [f"Blocked gate {gate}" for gate in blocked],
                next_actions=["Run or resolve all five gates before creating or reviewing an order draft."],
                evidence={"gate_statuses": {gate_type: gate.status for gate_type, gate in latest.items()}},
            )
        if warnings:
            return check(
                8,
                "decision_gates",
                "Decision Gates",
                "warn",
                f"Gate warnings require human review: {', '.join(warnings)}.",
                next_actions=["Document why the gate warnings are acceptable before approval."],
                evidence={"warnings": warnings},
            )
        return check(
            8,
            "decision_gates",
            "Decision Gates",
            "ok",
            "All five latest gates passed.",
            evidence={"gate_statuses": {gate_type: gate.status for gate_type, gate in latest.items()}},
        )

    def _risk_engine_check(self, intent: OrderIntent) -> dict[str, Any]:
        risk = self._latest_risk_check(intent.id)
        if risk is None:
            return check(
                9,
                "risk_engine",
                "Risk Engine",
                "block",
                "No completed risk check exists for this order intent.",
                blockers=["Missing latest RiskCheck."],
                next_actions=["Run the hard risk check before draft creation or approval."],
            )
        if not risk.hard_rule_passed:
            return check(
                9,
                "risk_engine",
                "Risk Engine",
                "block",
                risk.reason or "Latest risk check is blocked.",
                blockers=[risk.reason or "Latest RiskCheck failed hard rules."],
                next_actions=["Resolve failed hard risk rules before continuing."],
                related_entity_type="RiskCheck",
                related_entity_id=risk.id,
                evidence={"status": risk.status, "rules": risk.rules_json.get("rules", [])},
            )
        return check(
            9,
            "risk_engine",
            "Risk Engine",
            "ok",
            "Latest hard risk check passed.",
            related_entity_type="RiskCheck",
            related_entity_id=risk.id,
            evidence={"status": risk.status},
        )

    def _behavior_engine_check(self, intent: OrderIntent) -> dict[str, Any]:
        intervention = self._latest_behavior_intervention(intent.id)
        if intervention is None:
            return check(
                10,
                "behavior_engine",
                "Behavior Engine",
                "warn",
                "No behavior evaluation has been recorded for this order intent.",
                next_actions=["Evaluate behavior patterns before approval or paper execution."],
            )
        if intervention.intervention_level == "BLOCK":
            return check(
                10,
                "behavior_engine",
                "Behavior Engine",
                "block",
                "Latest behavior intervention is BLOCK.",
                blockers=["Behavior intervention level BLOCK cannot be bypassed."],
                next_actions=["Do not proceed; resolve the behavior intervention before continuing."],
                related_entity_type="BehaviorIntervention",
                related_entity_id=intervention.id,
            )
        if intervention.intervention_level == "HARD_CONFIRM" and not intervention.user_response:
            return check(
                10,
                "behavior_engine",
                "Behavior Engine",
                "warn",
                "Hard confirmation has not been answered.",
                next_actions=["Record the human response to the behavior intervention."],
                related_entity_type="BehaviorIntervention",
                related_entity_id=intervention.id,
                evidence={"intervention_level": intervention.intervention_level, "bypassed": intervention.bypassed},
            )
        status = "warn" if intervention.bypassed else "ok"
        return check(
            10,
            "behavior_engine",
            "Behavior Engine",
            status,
            "Behavior intervention was bypassed." if intervention.bypassed else "Latest behavior evaluation is recorded.",
            next_actions=["Review bypassed behavior intervention before approval."] if intervention.bypassed else [],
            related_entity_type="BehaviorIntervention",
            related_entity_id=intervention.id,
            evidence={"intervention_level": intervention.intervention_level, "bypassed": intervention.bypassed},
        )

    def _workflow_state_check(self, intent: OrderIntent, draft: OrderDraft | None) -> dict[str, Any]:
        workflow = self._latest_workflow(intent, draft)
        if workflow is None:
            return check(
                11,
                "workflow_state_machine",
                "Workflow State Machine",
                "warn",
                "No workflow state is linked to this order intent or draft.",
                next_actions=["Create or attach a workflow timeline so skipped gates remain auditable."],
            )
        if workflow.current_state == "BLOCKED":
            return check(
                11,
                "workflow_state_machine",
                "Workflow State Machine",
                "block",
                "Latest workflow state is BLOCKED.",
                blockers=[workflow.metadata_json.get("blocking_reason") or "Workflow is blocked."],
                next_actions=["Resolve the blocked workflow transition before continuing."],
                related_entity_type="WorkflowState",
                related_entity_id=workflow.id,
                evidence={"current_state": workflow.current_state, "previous_state": workflow.previous_state},
            )
        return check(
            11,
            "workflow_state_machine",
            "Workflow State Machine",
            "ok",
            f"Latest workflow state is {workflow.current_state}.",
            related_entity_type="WorkflowState",
            related_entity_id=workflow.id,
            evidence={"current_state": workflow.current_state, "previous_state": workflow.previous_state},
        )

    def _latest_draft(self, order_intent_id: str) -> OrderDraft | None:
        return self.db.scalar(
            select(OrderDraft)
            .where(OrderDraft.order_intent_id == order_intent_id)
            .order_by(OrderDraft.created_at.desc(), OrderDraft.id.desc())
            .limit(1)
        )

    def _latest_checkpoint(self, thesis_id: str) -> ThesisCheckpoint | None:
        return self.db.scalar(
            select(ThesisCheckpoint)
            .where(ThesisCheckpoint.thesis_id == thesis_id)
            .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
            .limit(1)
        )

    def _latest_gates(self, order_intent_id: str) -> dict[str, DecisionGate]:
        gates = list(
            self.db.scalars(
                select(DecisionGate)
                .where(DecisionGate.order_intent_id == order_intent_id)
                .order_by(DecisionGate.created_at.desc(), DecisionGate.id.desc())
            ).all()
        )
        latest: dict[str, DecisionGate] = {}
        for gate in gates:
            latest.setdefault(gate.gate_type, gate)
        return latest

    def _latest_risk_check(self, order_intent_id: str) -> RiskCheck | None:
        return self.db.scalar(
            select(RiskCheck)
            .where(RiskCheck.order_intent_id == order_intent_id)
            .order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc())
            .limit(1)
        )

    def _latest_behavior_intervention(self, order_intent_id: str) -> BehaviorIntervention | None:
        return self.db.scalar(
            select(BehaviorIntervention)
            .where(BehaviorIntervention.order_intent_id == order_intent_id)
            .order_by(BehaviorIntervention.created_at.desc(), BehaviorIntervention.id.desc())
            .limit(1)
        )

    def _latest_workflow(self, intent: OrderIntent, draft: OrderDraft | None) -> WorkflowState | None:
        entity_ids = [intent.id]
        if draft is not None:
            entity_ids.insert(0, draft.id)
        return self.db.scalar(
            select(WorkflowState)
            .where(WorkflowState.entity_id.in_(entity_ids))
            .order_by(WorkflowState.created_at.desc(), WorkflowState.id.desc())
            .limit(1)
        )

    def _title(self, intent: OrderIntent, asset: Asset | None, draft: OrderDraft | None) -> str:
        subject = "draft" if draft is not None else "intent"
        symbol = asset.symbol if asset else intent.asset_id
        return f"Stage 5-11 readiness for {symbol} {subject}"

    def _detail(self, readiness: str, checks: list[dict[str, Any]]) -> str:
        blocked = sum(1 for item in checks if item["status"] == "block")
        warnings = sum(1 for item in checks if item["status"] == "warn")
        if readiness == "blocked":
            return f"{blocked} stage checks are blocking this workflow."
        if readiness == "review_required":
            return f"{warnings} stage checks require human review."
        return "All stage 5-11 checks are ready for human review; execution remains unavailable."


def check(
    stage_number: int,
    stage_key: str,
    label: str,
    status: str,
    detail: str,
    *,
    blockers: list[str] | None = None,
    next_actions: list[str] | None = None,
    related_entity_type: str | None = None,
    related_entity_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "stage_number": stage_number,
        "stage_key": stage_key,
        "label": label,
        "status": status,
        "detail": detail,
        "blockers": blockers or [],
        "next_actions": next_actions or [],
        "related_entity_type": related_entity_type,
        "related_entity_id": related_entity_id,
        "evidence": evidence or {},
    }


def readiness_rank(readiness: str) -> int:
    return {"blocked": 0, "review_required": 1, "ready_for_human_review": 2}.get(readiness, 1)


def unique_list(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            seen.add(text)
            result.append(text)
    return result


def normalize_dt(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
