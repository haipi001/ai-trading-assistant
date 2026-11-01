from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import WorkflowState


WORKFLOW_STATES = [
    "IDEA_CREATED",
    "DATA_COLLECTED",
    "RESEARCH_GENERATED",
    "THESIS_CREATED_OR_MATCHED",
    "SIGNAL_DETECTED",
    "ORDER_INTENT_CREATED",
    "RESEARCH_GATE_PASSED",
    "THESIS_GATE_PASSED",
    "RISK_GATE_PASSED",
    "BEHAVIOR_GATE_PASSED",
    "EXECUTION_GATE_PASSED",
    "ORDER_DRAFT_CREATED",
    "USER_APPROVAL_REQUIRED",
    "APPROVED",
    "REJECTED",
    "MODIFIED",
    "PAPER_EXECUTED",
    "LIVE_EXECUTED",
    "EXECUTION_CONFIRMED",
    "JOURNAL_WRITTEN",
    "REVIEW_SCHEDULED",
    "POST_TRADE_REVIEWED",
    "PLAYBOOK_UPDATED",
    "BLOCKED",
]

LINEAR_TRANSITIONS = {
    "IDEA_CREATED": {"DATA_COLLECTED"},
    "DATA_COLLECTED": {"RESEARCH_GENERATED"},
    "RESEARCH_GENERATED": {"THESIS_CREATED_OR_MATCHED"},
    "THESIS_CREATED_OR_MATCHED": {"SIGNAL_DETECTED"},
    "SIGNAL_DETECTED": {"ORDER_INTENT_CREATED"},
    "ORDER_INTENT_CREATED": {"RESEARCH_GATE_PASSED"},
    "RESEARCH_GATE_PASSED": {"THESIS_GATE_PASSED"},
    "THESIS_GATE_PASSED": {"RISK_GATE_PASSED"},
    "RISK_GATE_PASSED": {"BEHAVIOR_GATE_PASSED"},
    "BEHAVIOR_GATE_PASSED": {"EXECUTION_GATE_PASSED"},
    "EXECUTION_GATE_PASSED": {"ORDER_DRAFT_CREATED"},
    "ORDER_DRAFT_CREATED": {"USER_APPROVAL_REQUIRED"},
    "USER_APPROVAL_REQUIRED": {"APPROVED", "REJECTED", "MODIFIED"},
    "MODIFIED": {"RESEARCH_GATE_PASSED"},
    "APPROVED": {"PAPER_EXECUTED", "LIVE_EXECUTED"},
    "PAPER_EXECUTED": {"EXECUTION_CONFIRMED"},
    "LIVE_EXECUTED": {"EXECUTION_CONFIRMED"},
    "EXECUTION_CONFIRMED": {"JOURNAL_WRITTEN"},
    "JOURNAL_WRITTEN": {"REVIEW_SCHEDULED"},
    "REVIEW_SCHEDULED": {"POST_TRADE_REVIEWED"},
    "POST_TRADE_REVIEWED": {"PLAYBOOK_UPDATED"},
}
TERMINAL_STATES = {"REJECTED", "PLAYBOOK_UPDATED", "BLOCKED"}
EXECUTION_STATES = {"PAPER_EXECUTED", "LIVE_EXECUTED"}
REQUIRED_GATES = ["RESEARCH_GATE_PASSED", "THESIS_GATE_PASSED", "RISK_GATE_PASSED", "BEHAVIOR_GATE_PASSED", "EXECUTION_GATE_PASSED"]


class WorkflowTransitionError(ValueError):
    pass


class WorkflowEngine:
    def __init__(self, db: Session):
        self.db = db

    def create_workflow(self, entity_type: str, entity_id: str, metadata: dict[str, Any] | None = None) -> WorkflowState:
        workflow = WorkflowState(
            workflow_type=entity_type,
            entity_id=entity_id,
            current_state="IDEA_CREATED",
            previous_state=None,
            transition_reason="workflow created",
            metadata_json=metadata or {},
        )
        self.db.add(workflow)
        self.db.flush()
        self._write_audit_log(
            action="workflow.created",
            entity_id=workflow.id,
            payload_json={"entity_type": entity_type, "entity_id": entity_id, "current_state": workflow.current_state},
        )
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def transition(
        self,
        workflow_id: str,
        next_state: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowState:
        current = self.get_workflow(workflow_id)
        self._ensure_latest_state(current)
        transition_metadata = metadata or {}
        try:
            self.validate_transition(current.current_state, next_state, transition_metadata, current)
        except WorkflowTransitionError as exc:
            self._record_blocked_transition(current, next_state, str(exc), transition_metadata)
            self.db.commit()
            raise

        workflow = WorkflowState(
            workflow_type=current.workflow_type,
            entity_id=current.entity_id,
            current_state=next_state,
            previous_state=current.current_state,
            transition_reason=reason,
            metadata_json=transition_metadata,
        )
        self.db.add(workflow)
        self.db.flush()
        self._write_audit_log(
            action="workflow.transitioned",
            entity_id=workflow.id,
            payload_json={
                "workflow_id": workflow_id,
                "entity_type": workflow.workflow_type,
                "entity_id": workflow.entity_id,
                "previous_state": current.current_state,
                "next_state": next_state,
                "reason": reason,
                "metadata": transition_metadata,
            },
        )
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def validate_transition(
        self,
        current_state: str,
        next_state: str,
        metadata: dict[str, Any] | None = None,
        workflow: WorkflowState | None = None,
    ) -> bool:
        transition_metadata = metadata or {}
        if current_state not in WORKFLOW_STATES:
            raise WorkflowTransitionError(f"unknown current workflow state: {current_state}")
        if next_state not in WORKFLOW_STATES:
            raise WorkflowTransitionError(f"unknown next workflow state: {next_state}")
        if current_state in TERMINAL_STATES:
            raise WorkflowTransitionError(f"cannot transition from terminal state {current_state}")
        if next_state == "BLOCKED":
            return True
        if next_state == "ORDER_DRAFT_CREATED" and current_state != "EXECUTION_GATE_PASSED":
            raise WorkflowTransitionError("cannot create OrderDraft before all required gates pass")
        if next_state in EXECUTION_STATES:
            self._validate_execution_transition(current_state, next_state, transition_metadata)
            return True
        if next_state == "PLAYBOOK_UPDATED" and current_state != "POST_TRADE_REVIEWED":
            raise WorkflowTransitionError("cannot update playbook before post-trade review")

        allowed_states = LINEAR_TRANSITIONS.get(current_state, set())
        if next_state not in allowed_states:
            raise WorkflowTransitionError(f"invalid transition from {current_state} to {next_state}")
        return True

    def block_workflow(self, workflow_id: str, reason: str, metadata: dict[str, Any] | None = None) -> WorkflowState:
        current = self.get_workflow(workflow_id)
        self._ensure_latest_state(current)
        workflow = WorkflowState(
            workflow_type=current.workflow_type,
            entity_id=current.entity_id,
            current_state="BLOCKED",
            previous_state=current.current_state,
            transition_reason=reason,
            metadata_json={"blocking_reason": reason, **(metadata or {})},
        )
        self.db.add(workflow)
        self.db.flush()
        self._write_audit_log(
            action="workflow.blocked",
            entity_id=workflow.id,
            payload_json={
                "workflow_id": workflow_id,
                "entity_type": workflow.workflow_type,
                "entity_id": workflow.entity_id,
                "previous_state": current.current_state,
                "blocking_reason": reason,
                "metadata": metadata or {},
            },
        )
        self.db.commit()
        self.db.refresh(workflow)
        return workflow

    def get_workflow(self, workflow_id: str) -> WorkflowState:
        workflow = self.db.get(WorkflowState, workflow_id)
        if workflow is None:
            raise WorkflowTransitionError("workflow not found")
        return workflow

    def get_workflow_timeline(self, entity_id: str, entity_type: str | None = None) -> list[WorkflowState]:
        statement = select(WorkflowState).where(WorkflowState.entity_id == entity_id)
        if entity_type is not None:
            statement = statement.where(WorkflowState.workflow_type == entity_type)
        return list(self.db.scalars(statement.order_by(WorkflowState.created_at, WorkflowState.id)).all())

    def _ensure_latest_state(self, workflow: WorkflowState) -> None:
        latest = self.db.scalar(
            select(WorkflowState)
            .where(WorkflowState.workflow_type == workflow.workflow_type, WorkflowState.entity_id == workflow.entity_id)
            .order_by(WorkflowState.created_at.desc(), WorkflowState.id.desc())
            .limit(1)
        )
        if latest is not None and latest.id != workflow.id:
            raise WorkflowTransitionError("workflow_id is not the latest state for this entity")

    def _validate_execution_transition(self, current_state: str, next_state: str, metadata: dict[str, Any]) -> None:
        automation_level = metadata.get("automation_level")
        if current_state != "APPROVED" and automation_level != "A5_CONTROLLED_AUTO":
            raise WorkflowTransitionError("cannot execute before approval unless AutomationPolicy allows A5_CONTROLLED_AUTO")
        if next_state == "LIVE_EXECUTED" and not bool(metadata.get("live_trading_enabled", False)):
            raise WorkflowTransitionError("cannot live execute unless live_trading_enabled is true")

    def _record_blocked_transition(
        self,
        current: WorkflowState,
        next_state: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> WorkflowState:
        blocked = WorkflowState(
            workflow_type=current.workflow_type,
            entity_id=current.entity_id,
            current_state="BLOCKED",
            previous_state=current.current_state,
            transition_reason=reason,
            metadata_json={"attempted_state": next_state, "blocking_reason": reason, **metadata},
        )
        self.db.add(blocked)
        self.db.flush()
        self._write_audit_log(
            action="workflow.transition_blocked",
            entity_id=blocked.id,
            payload_json={
                "workflow_id": current.id,
                "entity_type": current.workflow_type,
                "entity_id": current.entity_id,
                "previous_state": current.current_state,
                "attempted_state": next_state,
                "blocking_reason": reason,
                "metadata": metadata,
            },
        )
        return blocked

    def _write_audit_log(self, *, action: str, entity_id: str, payload_json: dict[str, Any]) -> AuditLog:
        audit_log = AuditLog(
            actor_type="system",
            actor_id="workflow-engine",
            action=action,
            entity_type="WorkflowState",
            entity_id=entity_id,
            payload_json=payload_json,
        )
        self.db.add(audit_log)
        return audit_log
