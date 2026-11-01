from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.domain import write_audit_log
from app.models import Asset
from app.models import DecisionGate
from app.models import Execution
from app.models import InvestmentThesis
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PlaybookUpdateProposal
from app.models import PostTradeReview
from app.models import StrategyPlaybook
from app.models import ThesisCheckpoint
from app.models import WorkflowReviewTask


REQUIRED_GATE_TYPES = {"RESEARCH_GATE", "THESIS_GATE", "RISK_GATE", "BEHAVIOR_GATE", "EXECUTION_GATE"}


class WorkflowDeepReviewService:
    def __init__(self, db: Session):
        self.db = db

    def queue(self, *, user_id: str = "default-user", limit: int = 25) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        items: list[dict[str, Any]] = []
        items.extend(self._thesis_items(user_id=user_id, generated_at=generated_at))
        items.extend(self._draft_items(user_id=user_id))
        items.extend(self._review_items(user_id=user_id))
        items.extend(self._proposal_items(user_id=user_id))
        items.sort(key=lambda row: (priority_rank(row["priority"]), row["title"]))
        self._attach_task_state(user_id=user_id, items=items)
        items = items[:limit]
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "total_items": len(items),
            "high_priority_count": sum(1 for row in items if row["priority"] == "high"),
            "blocked_count": sum(1 for row in items if row["blockers"]),
            "execution_available": False,
            "items": items,
        }

    def sync_automatic_tasks(self, *, user_id: str = "default-user") -> dict[str, int]:
        """Persist human-review work detected by the deep-review queue.

        This deliberately creates review tasks, never thesis checkpoints or review
        conclusions: those records contain human judgement and must remain manual.
        """
        eligible_types = {"thesis_monitor_due", "post_trade_review_pending"}
        detected = [row for row in self.queue(user_id=user_id, limit=500)["items"] if row["item_type"] in eligible_types]
        active_ids = {row["id"] for row in detected}
        created = 0
        updated = 0
        for row in detected:
            existed = row.get("task_id") is not None
            self.assign_task(
                user_id=user_id,
                queue_item_id=row["id"],
                item_type=row["item_type"],
                title=row["title"],
                detail=row["detail"],
                priority=row["priority"],
                due_at=datetime.now(timezone.utc),
                related_entity_type=row["related_entity_type"],
                related_entity_id=row["related_entity_id"],
                payload_json={
                    "auto_generated": True,
                    "requires_human_verdict": True,
                    "stage": row["stage"],
                    "source": row["source"],
                    "next_action": row["next_action"],
                },
            )
            updated += int(existed)
            created += int(not existed)

        stale_tasks = list(
            self.db.scalars(
                select(WorkflowReviewTask).where(
                    WorkflowReviewTask.user_id == user_id,
                    WorkflowReviewTask.status.in_(["open", "in_progress"]),
                    WorkflowReviewTask.item_type.in_(eligible_types),
                )
            ).all()
        )
        resolved = 0
        for task in stale_tasks:
            if task.payload_json.get("auto_generated") is not True or task.queue_item_id in active_ids:
                continue
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            write_audit_log(
                self.db,
                action="workflow_review_task.auto_resolved",
                entity_type="WorkflowReviewTask",
                entity_id=task.id,
                payload_json={"user_id": user_id, "queue_item_id": task.queue_item_id, "execution_available": False},
                actor_id="workflow-review-service",
            )
            resolved += 1
        if resolved:
            self.db.commit()
        return {"detected": len(detected), "created": created, "updated": updated, "resolved": resolved}

    def list_tasks(
        self,
        *,
        user_id: str = "default-user",
        status: str | None = None,
        limit: int = 50,
    ) -> list[WorkflowReviewTask]:
        query = select(WorkflowReviewTask).where(WorkflowReviewTask.user_id == user_id)
        if status:
            query = query.where(WorkflowReviewTask.status == status)
        return list(
            self.db.scalars(
                query.order_by(WorkflowReviewTask.updated_at.desc(), WorkflowReviewTask.id.desc()).limit(limit)
            ).all()
        )

    def assign_task(self, **payload: Any) -> WorkflowReviewTask:
        user_id = str(payload.get("user_id") or "default-user")
        queue_item_id = str(payload.get("queue_item_id") or "").strip()
        if not queue_item_id:
            raise ValueError("queue_item_id is required")
        task = self.db.scalar(
            select(WorkflowReviewTask)
            .where(
                WorkflowReviewTask.user_id == user_id,
                WorkflowReviewTask.queue_item_id == queue_item_id,
                WorkflowReviewTask.status.in_(["open", "in_progress"]),
            )
            .order_by(WorkflowReviewTask.updated_at.desc(), WorkflowReviewTask.id.desc())
            .limit(1)
        )
        if task is None:
            task = WorkflowReviewTask(
                user_id=user_id,
                queue_item_id=queue_item_id,
                item_type=str(payload.get("item_type") or "review"),
                title=str(payload.get("title") or "Review task"),
                detail=str(payload.get("detail") or ""),
                priority=str(payload.get("priority") or "normal"),
                status="open",
                assignee_id=payload.get("assignee_id"),
                due_at=payload.get("due_at"),
                related_entity_type=str(payload.get("related_entity_type") or "Unknown"),
                related_entity_id=str(payload.get("related_entity_id") or queue_item_id),
                payload_json=payload.get("payload_json") or {},
            )
            self.db.add(task)
            action = "workflow_review_task.created"
        else:
            task.item_type = str(payload.get("item_type") or task.item_type)
            task.title = str(payload.get("title") or task.title)
            task.detail = str(payload.get("detail") or task.detail)
            task.priority = str(payload.get("priority") or task.priority)
            task.assignee_id = payload.get("assignee_id") or task.assignee_id
            task.due_at = payload.get("due_at") or task.due_at
            task.related_entity_type = str(payload.get("related_entity_type") or task.related_entity_type)
            task.related_entity_id = str(payload.get("related_entity_id") or task.related_entity_id)
            task.payload_json = payload.get("payload_json") or task.payload_json
            action = "workflow_review_task.updated"
        self.db.flush()
        write_audit_log(
            self.db,
            action=action,
            entity_type="WorkflowReviewTask",
            entity_id=task.id,
            payload_json={
                "user_id": task.user_id,
                "queue_item_id": task.queue_item_id,
                "item_type": task.item_type,
                "assignee_id": task.assignee_id,
                "execution_available": False,
            },
            actor_id="workflow-review-service",
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def complete_task(self, *, task_id: str, user_id: str = "default-user") -> WorkflowReviewTask:
        task = self.db.scalar(
            select(WorkflowReviewTask)
            .where(WorkflowReviewTask.id == task_id, WorkflowReviewTask.user_id == user_id)
            .limit(1)
        )
        if task is None:
            raise ValueError("workflow review task not found")
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        self.db.flush()
        write_audit_log(
            self.db,
            action="workflow_review_task.completed",
            entity_type="WorkflowReviewTask",
            entity_id=task.id,
            payload_json={"user_id": user_id, "queue_item_id": task.queue_item_id, "execution_available": False},
            actor_id="workflow-review-service",
        )
        self.db.commit()
        self.db.refresh(task)
        return task

    def _thesis_items(self, *, user_id: str, generated_at: datetime) -> list[dict[str, Any]]:
        theses = list(
            self.db.scalars(
                select(InvestmentThesis)
                .where(InvestmentThesis.user_id == user_id, InvestmentThesis.status.in_(["active", "monitoring"]))
                .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
                .limit(100)
            ).all()
        )
        stale_threshold = generated_at - timedelta(days=14)
        items: list[dict[str, Any]] = []
        for thesis in theses:
            latest_checkpoint = self.db.scalar(
                select(ThesisCheckpoint)
                .where(ThesisCheckpoint.thesis_id == thesis.id)
                .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
                .limit(1)
            )
            if latest_checkpoint and normalize_dt(latest_checkpoint.created_at) >= stale_threshold:
                continue
            asset = self.db.get(Asset, thesis.asset_id)
            items.append(
                item(
                    item_id=f"thesis:{thesis.id}",
                    item_type="thesis_monitor_due",
                    priority="high" if latest_checkpoint is None else "normal",
                    title=f"Review thesis for {asset.symbol if asset else thesis.asset_id}",
                    detail="No recent thesis checkpoint exists." if latest_checkpoint is None else "Latest thesis checkpoint is older than 14 days.",
                    stage="thesis_monitor",
                    source="investment_thesis",
                    related_entity_type="InvestmentThesis",
                    related_entity_id=thesis.id,
                    asset_id=thesis.asset_id,
                    asset_symbol=asset.symbol if asset else None,
                    thesis_id=thesis.id,
                    next_action="Run or record a thesis monitor checkpoint before relying on this position or any new order draft.",
                    blockers=[] if latest_checkpoint else ["Thesis has never been checked against fresh facts."],
                )
            )
        return items

    def _draft_items(self, *, user_id: str) -> list[dict[str, Any]]:
        drafts = list(self.db.scalars(select(OrderDraft).order_by(OrderDraft.created_at.desc(), OrderDraft.id.desc()).limit(100)).all())
        items: list[dict[str, Any]] = []
        for draft in drafts:
            intent = self.db.get(OrderIntent, draft.order_intent_id)
            if intent is None:
                continue
            thesis = self.db.get(InvestmentThesis, intent.investment_thesis_id) if intent.investment_thesis_id else None
            if thesis is not None and thesis.user_id != user_id:
                continue
            asset = self.db.get(Asset, intent.asset_id)
            latest_gates = self._latest_gates(intent.id)
            missing_gates = sorted(REQUIRED_GATE_TYPES - set(latest_gates))
            blocked_gates = [gate_type for gate_type, gate in latest_gates.items() if gate.status == "BLOCKED"]
            warnings = [gate_type for gate_type, gate in latest_gates.items() if gate.status in {"WARNING", "HARD_CONFIRM_REQUIRED"}]

            if thesis is None:
                items.append(
                    item(
                        item_id=f"draft-thesis:{draft.id}",
                        item_type="missing_thesis_link",
                        priority="high",
                        title=f"Link thesis before reviewing {asset.symbol if asset else intent.asset_id} draft",
                        detail="Order intent has no explicit investment thesis.",
                        stage="thesis_gate",
                        source="order_draft",
                        related_entity_type="OrderDraft",
                        related_entity_id=draft.id,
                        asset_id=intent.asset_id,
                        asset_symbol=asset.symbol if asset else None,
                        order_intent_id=intent.id,
                        order_draft_id=draft.id,
                        next_action="Create or attach an active investment thesis before approval or paper execution.",
                        blockers=["Missing investment thesis link."],
                    )
                )

            if missing_gates or blocked_gates:
                items.append(
                    item(
                        item_id=f"draft-gates:{draft.id}",
                        item_type="gate_evidence_incomplete",
                        priority="high",
                        title=f"Resolve gates for {asset.symbol if asset else intent.asset_id}",
                        detail=f"Missing gates: {', '.join(missing_gates) or 'none'}; blocked gates: {', '.join(blocked_gates) or 'none'}.",
                        stage="decision_gates",
                        source="decision_gate",
                        related_entity_type="OrderDraft",
                        related_entity_id=draft.id,
                        asset_id=intent.asset_id,
                        asset_symbol=asset.symbol if asset else None,
                        thesis_id=thesis.id if thesis else None,
                        order_intent_id=intent.id,
                        order_draft_id=draft.id,
                        next_action="Re-run or resolve ResearchGate, ThesisGate, RiskGate, BehaviorGate, and ExecutionGate before approval.",
                        blockers=[*missing_gates, *blocked_gates],
                    )
                )
            elif warnings:
                items.append(
                    item(
                        item_id=f"draft-warnings:{draft.id}",
                        item_type="gate_warning_review",
                        priority="normal",
                        title=f"Review gate warnings for {asset.symbol if asset else intent.asset_id}",
                        detail=f"Warnings require explicit human review: {', '.join(warnings)}.",
                        stage="decision_gates",
                        source="decision_gate",
                        related_entity_type="OrderDraft",
                        related_entity_id=draft.id,
                        asset_id=intent.asset_id,
                        asset_symbol=asset.symbol if asset else None,
                        thesis_id=thesis.id if thesis else None,
                        order_intent_id=intent.id,
                        order_draft_id=draft.id,
                        next_action="Document the reason for accepting or rejecting gate warnings.",
                    )
                )

            if draft.approval_status == "approved" and not self._executions(draft.id):
                items.append(
                    item(
                        item_id=f"draft-approved:{draft.id}",
                        item_type="approved_draft_waiting_paper",
                        priority="normal",
                        title=f"Approved paper-only draft for {asset.symbol if asset else intent.asset_id}",
                        detail="Draft is approved but has no paper execution record.",
                        stage="paper_execution",
                        source="approval",
                        related_entity_type="OrderDraft",
                        related_entity_id=draft.id,
                        asset_id=intent.asset_id,
                        asset_symbol=asset.symbol if asset else None,
                        thesis_id=thesis.id if thesis else None,
                        order_intent_id=intent.id,
                        order_draft_id=draft.id,
                        next_action="Use paper execution only if the approval is still valid; live execution remains unavailable.",
                    )
                )
        return items

    def _review_items(self, *, user_id: str) -> list[dict[str, Any]]:
        reviews = list(
            self.db.scalars(
                select(PostTradeReview)
                .where(PostTradeReview.user_id == user_id)
                .order_by(PostTradeReview.updated_at.desc(), PostTradeReview.id.desc())
                .limit(100)
            ).all()
        )
        items: list[dict[str, Any]] = []
        for review in reviews:
            draft = self.db.get(OrderDraft, review.order_draft_id)
            intent = self.db.get(OrderIntent, draft.order_intent_id) if draft else None
            asset = self.db.get(Asset, intent.asset_id) if intent else None
            if review.status != "completed":
                items.append(
                    item(
                        item_id=f"review:{review.id}",
                        item_type="post_trade_review_pending",
                        priority="high",
                        title=f"Complete post-trade review for {asset.symbol if asset else review.order_draft_id}",
                        detail="Paper execution exists, but the learning loop is still pending.",
                        stage="post_trade_review",
                        source="post_trade_review",
                        related_entity_type="PostTradeReview",
                        related_entity_id=review.id,
                        asset_id=intent.asset_id if intent else None,
                        asset_symbol=asset.symbol if asset else None,
                        thesis_id=intent.investment_thesis_id if intent else None,
                        order_intent_id=intent.id if intent else None,
                        order_draft_id=review.order_draft_id,
                        review_id=review.id,
                        next_action="Complete the structured post-trade review before updating playbooks or taking follow-on actions.",
                        blockers=["Post-trade review is pending."],
                    )
                )
                continue
            if self._proposal_for_review(review.id) is None:
                items.append(
                    item(
                        item_id=f"review-proposal:{review.id}",
                        item_type="review_without_playbook_proposal",
                        priority="normal",
                        title=f"Decide if {asset.symbol if asset else 'trade'} lesson updates the playbook",
                        detail="Completed review has no playbook update proposal.",
                        stage="playbook_learning",
                        source="post_trade_review",
                        related_entity_type="PostTradeReview",
                        related_entity_id=review.id,
                        asset_id=intent.asset_id if intent else None,
                        asset_symbol=asset.symbol if asset else None,
                        thesis_id=intent.investment_thesis_id if intent else None,
                        order_intent_id=intent.id if intent else None,
                        order_draft_id=review.order_draft_id,
                        review_id=review.id,
                        next_action="Create a manual playbook proposal only if the review lesson should become a durable rule.",
                    )
                )
        return items

    def _proposal_items(self, *, user_id: str) -> list[dict[str, Any]]:
        proposals = list(
            self.db.scalars(
                select(PlaybookUpdateProposal)
                .where(
                    PlaybookUpdateProposal.user_id == user_id,
                    PlaybookUpdateProposal.status.in_(["pending", "approved_pending_manual_apply"]),
                )
                .order_by(PlaybookUpdateProposal.created_at.desc(), PlaybookUpdateProposal.id.desc())
                .limit(100)
            ).all()
        )
        items: list[dict[str, Any]] = []
        for proposal in proposals:
            playbook = self.db.get(StrategyPlaybook, proposal.strategy_playbook_id) if proposal.strategy_playbook_id else None
            items.append(
                item(
                    item_id=f"proposal:{proposal.id}",
                    item_type="playbook_proposal_review",
                    priority="normal",
                    title=f"Review playbook proposal for {playbook.name if playbook else 'unlinked playbook'}",
                    detail=proposal.rationale,
                    stage="playbook_learning",
                    source="playbook_update_proposal",
                    related_entity_type="PlaybookUpdateProposal",
                    related_entity_id=proposal.id,
                    next_action="Approve, reject, or manually apply the proposal; never auto-apply review lessons.",
                )
            )
        return items

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

    def _executions(self, order_draft_id: str) -> list[Execution]:
        return list(
            self.db.scalars(
                select(Execution)
                .where(Execution.order_draft_id == order_draft_id)
                .order_by(Execution.created_at.desc(), Execution.id.desc())
            ).all()
        )

    def _proposal_for_review(self, review_id: str) -> PlaybookUpdateProposal | None:
        return self.db.scalar(
            select(PlaybookUpdateProposal)
            .where(
                PlaybookUpdateProposal.source_type == "post_trade_review",
                PlaybookUpdateProposal.source_id == review_id,
            )
            .order_by(PlaybookUpdateProposal.created_at.desc(), PlaybookUpdateProposal.id.desc())
            .limit(1)
        )

    def _attach_task_state(self, *, user_id: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        item_ids = [row["id"] for row in items]
        tasks = list(
            self.db.scalars(
                select(WorkflowReviewTask)
                .where(
                    WorkflowReviewTask.user_id == user_id,
                    WorkflowReviewTask.queue_item_id.in_(item_ids),
                    WorkflowReviewTask.status.in_(["open", "in_progress"]),
                )
                .order_by(WorkflowReviewTask.updated_at.desc(), WorkflowReviewTask.id.desc())
            ).all()
        )
        task_by_item: dict[str, WorkflowReviewTask] = {}
        for task in tasks:
            task_by_item.setdefault(task.queue_item_id, task)
        for row in items:
            task = task_by_item.get(row["id"])
            if task is None:
                row.update({"task_id": None, "assignment_status": "unassigned", "assignee_id": None, "due_at": None})
            else:
                row.update(
                    {
                        "task_id": task.id,
                        "assignment_status": task.status,
                        "assignee_id": task.assignee_id,
                        "due_at": task.due_at,
                    }
                )


def item(
    *,
    item_id: str,
    item_type: str,
    priority: str,
    title: str,
    detail: str,
    stage: str,
    source: str,
    related_entity_type: str,
    related_entity_id: str,
    next_action: str,
    asset_id: str | None = None,
    asset_symbol: str | None = None,
    thesis_id: str | None = None,
    order_intent_id: str | None = None,
    order_draft_id: str | None = None,
    review_id: str | None = None,
    blockers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "item_type": item_type,
        "priority": priority,
        "title": title,
        "detail": detail,
        "stage": stage,
        "source": source,
        "related_entity_type": related_entity_type,
        "related_entity_id": related_entity_id,
        "asset_id": asset_id,
        "asset_symbol": asset_symbol,
        "thesis_id": thesis_id,
        "order_intent_id": order_intent_id,
        "order_draft_id": order_draft_id,
        "review_id": review_id,
        "next_action": next_action,
        "blockers": blockers or [],
        "task_id": None,
        "assignment_status": "unassigned",
        "assignee_id": None,
        "due_at": None,
        "execution_available": False,
    }


def priority_rank(priority: str) -> int:
    return {"high": 0, "normal": 1, "low": 2}.get(priority, 1)


def normalize_dt(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
