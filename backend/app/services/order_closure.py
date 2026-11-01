from datetime import datetime
from datetime import timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Approval
from app.models import Asset
from app.models import DecisionGate
from app.models import Execution
from app.models import InvestmentThesis
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PostTradeReview
from app.models import RiskCheck
from app.services.stage_readiness import REQUIRED_GATE_TYPES
from app.services.stage_readiness import unique_list


class OrderClosureService:
    def __init__(self, db: Session):
        self.db = db

    def report(self, *, user_id: str = "default-user", limit: int = 25) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        drafts = list(
            self.db.scalars(
                select(OrderDraft)
                .order_by(OrderDraft.created_at.desc(), OrderDraft.id.desc())
                .limit(max(limit, 100))
            ).all()
        )
        items = [self._item_for_draft(draft) for draft in drafts]
        items.sort(key=lambda item: (closure_rank(item["status"]), item["asset_symbol"] or "", item["created_at"]))
        items = items[:limit]
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "total_items": len(items),
            "closed_count": sum(1 for item in items if item["status"] == "closed"),
            "review_required_count": sum(1 for item in items if item["status"] == "review_required"),
            "blocked_count": sum(1 for item in items if item["status"] == "blocked"),
            "execution_available": False,
            "items": items,
        }

    def quality_report(self, *, user_id: str = "default-user", limit: int = 25) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        closure = self.report(user_id=user_id, limit=limit)
        items = [quality_item(item) for item in closure["items"]]
        average_score = sum(item["quality_score"] for item in items) / len(items) if items else 0
        hard_gaps = [gap for item in items for gap in item["hard_gaps"]]
        explanation_gaps = [gap for item in items for gap in item["explanation_gaps"]]
        if hard_gaps:
            status = "blocked"
        elif explanation_gaps or any(item["status"] == "review_required" for item in items):
            status = "review_required"
        else:
            status = "closed_loop_ready"
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": status,
            "average_quality_score": round(average_score, 4),
            "total_items": len(items),
            "closed_count": closure["closed_count"],
            "review_required_count": closure["review_required_count"],
            "blocked_count": closure["blocked_count"],
            "hard_gaps": unique_list(hard_gaps),
            "explanation_gaps": unique_list(explanation_gaps),
            "next_actions": unique_list(action for item in items for action in item["next_actions"]),
            "execution_available": False,
            "items": items,
        }

    def review_action_plan(self, *, user_id: str = "default-user", limit: int = 25) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc)
        quality = self.quality_report(user_id=user_id, limit=limit)
        action_items: list[dict[str, Any]] = []
        for item in quality["items"]:
            for gap in item["hard_gaps"]:
                action_items.append(
                    review_action_item(
                        item=item,
                        gap_type="hard_gap",
                        priority="P0",
                        gap=gap,
                        suggested_action="Resolve the blocking workflow gap before this draft can be treated as closed.",
                    )
                )
            for gap in item["explanation_gaps"]:
                action_items.append(
                    review_action_item(
                        item=item,
                        gap_type="explanation_gap",
                        priority="P1",
                        gap=gap,
                        suggested_action="Capture missing rationale, gate explanation, or post-trade learning before playbook updates.",
                    )
                )
            if not item["hard_gaps"] and not item["explanation_gaps"] and item["next_actions"]:
                action_items.append(
                    review_action_item(
                        item=item,
                        gap_type="follow_up",
                        priority="P2",
                        gap=item["next_actions"][0],
                        suggested_action=item["next_actions"][0],
                    )
                )
        if any(action["priority"] == "P0" for action in action_items):
            status = "blocked"
        elif action_items:
            status = "review_required"
        else:
            status = "ready_for_playbook_review"
        return {
            "user_id": user_id,
            "generated_at": generated_at,
            "status": status,
            "quality_status": quality["status"],
            "average_quality_score": quality["average_quality_score"],
            "action_count": len(action_items),
            "p0_count": sum(1 for item in action_items if item["priority"] == "P0"),
            "p1_count": sum(1 for item in action_items if item["priority"] == "P1"),
            "next_actions": unique_list(
                [item["suggested_action"] for item in action_items]
                + ["Do not apply playbook changes automatically; require human review before manual apply."]
            ),
            "actions": action_items,
            "execution_available": False,
        }

    def _item_for_draft(self, draft: OrderDraft) -> dict[str, Any]:
        intent = self.db.get(OrderIntent, draft.order_intent_id)
        asset = self.db.get(Asset, intent.asset_id) if intent is not None else None
        latest_execution = self._latest_execution(draft.id)
        latest_review = self._latest_review(draft.id)
        checks = [
            self._thesis_or_rationale_check(intent),
            self._order_draft_check(draft),
            self._decision_gates_check(intent),
            self._risk_check(intent),
            self._approval_check(draft),
            self._paper_execution_check(draft, latest_execution),
            self._post_trade_review_check(latest_execution, latest_review),
            self._safety_boundary_check(latest_execution),
        ]
        blockers = [blocker for check in checks for blocker in check["blockers"]]
        next_actions = unique_list(action for check in checks for action in check["next_actions"])
        if any(check["status"] == "block" for check in checks):
            status = "blocked"
        elif any(check["status"] == "warn" for check in checks):
            status = "review_required"
        else:
            status = "closed"
        return {
            "id": f"order-closure:{draft.id}",
            "status": status,
            "title": self._title(intent, asset, draft),
            "detail": self._detail(status, checks),
            "asset_id": intent.asset_id if intent is not None else None,
            "asset_symbol": asset.symbol if asset is not None else None,
            "order_intent_id": intent.id if intent is not None else None,
            "order_draft_id": draft.id,
            "thesis_id": intent.investment_thesis_id if intent is not None else None,
            "execution_id": latest_execution.id if latest_execution is not None else None,
            "post_trade_review_id": latest_review.id if latest_review is not None else None,
            "blockers": blockers,
            "next_actions": next_actions,
            "checks": checks,
            "created_at": draft.created_at,
            "execution_available": False,
        }

    def _thesis_or_rationale_check(self, intent: OrderIntent | None) -> dict[str, Any]:
        if intent is None:
            return closure_check(
                "thesis_or_rationale",
                "Thesis Or Rationale",
                "block",
                "Order draft is missing its linked order intent.",
                blockers=["Missing linked OrderIntent."],
                next_actions=["Repair the draft-intent linkage before continuing review."],
            )
        thesis = self.db.get(InvestmentThesis, intent.investment_thesis_id) if intent.investment_thesis_id else None
        explicit_rationale = bool((intent.user_rationale or intent.rationale or "").strip())
        if thesis is None:
            if explicit_rationale:
                return closure_check(
                    "thesis_or_rationale",
                    "Thesis Or Rationale",
                    "ok",
                    "Explicit order rationale is captured without a linked thesis.",
                    related_entity_type="OrderIntent",
                    related_entity_id=intent.id,
                    evidence={"has_explicit_rationale": True},
                )
            return closure_check(
                "thesis_or_rationale",
                "Thesis Or Rationale",
                "block",
                "No linked thesis or explicit order rationale exists.",
                blockers=["Missing InvestmentThesis or explicit order rationale."],
                next_actions=["Attach an InvestmentThesis or capture explicit human rationale."],
                related_entity_type="OrderIntent",
                related_entity_id=intent.id,
            )
        if thesis.status not in {"active", "monitoring"}:
            return closure_check(
                "thesis_or_rationale",
                "Thesis Or Rationale",
                "block",
                f"Linked thesis is {thesis.status}.",
                blockers=[f"InvestmentThesis status is {thesis.status}, not active/monitoring."],
                next_actions=["Update, replace, or close the thesis before considering the order closed."],
                related_entity_type="InvestmentThesis",
                related_entity_id=thesis.id,
                evidence={"status": thesis.status},
            )
        return closure_check(
            "thesis_or_rationale",
            "Thesis Or Rationale",
            "ok",
            "Linked thesis is active or monitoring.",
            related_entity_type="InvestmentThesis",
            related_entity_id=thesis.id,
            evidence={"status": thesis.status, "confidence": float(thesis.confidence)},
        )

    def _order_draft_check(self, draft: OrderDraft) -> dict[str, Any]:
        return closure_check(
            "order_draft",
            "Order Draft",
            "ok",
            "Order draft exists and carries the latest risk, approval, and execution statuses.",
            related_entity_type="OrderDraft",
            related_entity_id=draft.id,
            evidence={
                "risk_status": draft.risk_status,
                "behavior_status": draft.behavior_status,
                "approval_status": draft.approval_status,
                "execution_status": draft.execution_status,
            },
        )

    def _decision_gates_check(self, intent: OrderIntent | None) -> dict[str, Any]:
        if intent is None:
            return closure_check(
                "decision_gates",
                "Decision Gates",
                "block",
                "Decision gates cannot be evaluated without an order intent.",
                blockers=["Missing OrderIntent for DecisionGate lookup."],
                next_actions=["Repair the draft-intent linkage before replaying gates."],
            )
        latest = self._latest_gates(intent.id)
        missing = sorted(REQUIRED_GATE_TYPES - set(latest))
        blocked = [gate_type for gate_type, gate in latest.items() if gate.status == "BLOCKED"]
        warnings = [gate_type for gate_type, gate in latest.items() if gate.status in {"WARNING", "HARD_CONFIRM_REQUIRED"}]
        statuses = {gate_type: gate.status for gate_type, gate in latest.items()}
        if missing or blocked:
            return closure_check(
                "decision_gates",
                "Decision Gates",
                "block",
                f"Missing gates: {', '.join(missing) or 'none'}; blocked gates: {', '.join(blocked) or 'none'}.",
                blockers=[f"Missing gate {gate}" for gate in missing] + [f"Blocked gate {gate}" for gate in blocked],
                next_actions=["Run or resolve all five gates before treating this draft as closed."],
                evidence={"gate_statuses": statuses},
            )
        if warnings:
            return closure_check(
                "decision_gates",
                "Decision Gates",
                "warn",
                f"Gate warnings require human review: {', '.join(warnings)}.",
                next_actions=["Document why gate warnings are acceptable before final closure."],
                evidence={"gate_statuses": statuses, "warnings": warnings},
            )
        return closure_check(
            "decision_gates",
            "Decision Gates",
            "ok",
            "All five latest gates passed.",
            evidence={"gate_statuses": statuses},
        )

    def _risk_check(self, intent: OrderIntent | None) -> dict[str, Any]:
        if intent is None:
            return closure_check(
                "risk_check",
                "Risk Check",
                "block",
                "Risk check cannot be evaluated without an order intent.",
                blockers=["Missing OrderIntent for RiskCheck lookup."],
                next_actions=["Repair the draft-intent linkage before rerunning risk checks."],
            )
        risk = self._latest_risk_check(intent.id)
        if risk is None:
            return closure_check(
                "risk_check",
                "Risk Check",
                "block",
                "No completed risk check exists for this order intent.",
                blockers=["Missing latest RiskCheck."],
                next_actions=["Run the hard risk check before approval, execution, or closure."],
            )
        if not risk.hard_rule_passed:
            return closure_check(
                "risk_check",
                "Risk Check",
                "block",
                risk.reason or "Latest risk check failed hard rules.",
                blockers=[risk.reason or "Latest RiskCheck failed hard rules."],
                next_actions=["Resolve failed hard risk rules before continuing."],
                related_entity_type="RiskCheck",
                related_entity_id=risk.id,
                evidence={"status": risk.status, "rules": risk.rules_json.get("rules", [])},
            )
        return closure_check(
            "risk_check",
            "Risk Check",
            "ok",
            "Latest hard risk check passed.",
            related_entity_type="RiskCheck",
            related_entity_id=risk.id,
            evidence={"status": risk.status},
        )

    def _approval_check(self, draft: OrderDraft) -> dict[str, Any]:
        approval = self._latest_approval(draft.id)
        if draft.approval_status == "approved":
            return closure_check(
                "approval",
                "Human Approval",
                "ok",
                "Order draft has human approval recorded.",
                related_entity_type="Approval" if approval is not None else "OrderDraft",
                related_entity_id=approval.id if approval is not None else draft.id,
                evidence={"draft_approval_status": draft.approval_status, "approval_status": approval.status if approval else None},
            )
        if draft.approval_status == "rejected" or (approval is not None and approval.status == "rejected"):
            return closure_check(
                "approval",
                "Human Approval",
                "block",
                "Order draft was rejected.",
                blockers=["Rejected drafts cannot be closed as completed order workflows."],
                next_actions=["Create a new intent/draft if the trade still has a valid thesis and risk profile."],
                related_entity_type="Approval" if approval is not None else "OrderDraft",
                related_entity_id=approval.id if approval is not None else draft.id,
                evidence={"draft_approval_status": draft.approval_status, "approval_status": approval.status if approval else None},
            )
        return closure_check(
            "approval",
            "Human Approval",
            "warn",
            f"Order draft approval status is {draft.approval_status}.",
            next_actions=["Approve, reject, or request modification before paper execution or final closure."],
            related_entity_type="OrderDraft",
            related_entity_id=draft.id,
            evidence={"draft_approval_status": draft.approval_status, "approval_status": approval.status if approval else None},
        )

    def _paper_execution_check(self, draft: OrderDraft, execution: Execution | None) -> dict[str, Any]:
        if execution is None:
            next_action = "Paper execute the approved draft when the human reviewer is ready." if draft.approval_status == "approved" else "Resolve approval before paper execution."
            return closure_check(
                "paper_execution",
                "Paper Execution",
                "warn",
                "No paper execution exists for this draft.",
                next_actions=[next_action],
                related_entity_type="OrderDraft",
                related_entity_id=draft.id,
                evidence={"draft_execution_status": draft.execution_status},
            )
        if execution.execution_mode != "paper":
            return closure_check(
                "paper_execution",
                "Paper Execution",
                "block",
                f"Latest execution mode is {execution.execution_mode}, not paper.",
                blockers=["Order closure safe slice only accepts paper execution records."],
                next_actions=["Review live execution controls and reconcile this draft outside the paper-only closure report."],
                related_entity_type="Execution",
                related_entity_id=execution.id,
                evidence={"execution_mode": execution.execution_mode, "status": execution.status},
            )
        if execution.status in {"filled", "partially_filled"}:
            return closure_check(
                "paper_execution",
                "Paper Execution",
                "ok",
                f"Latest paper execution is {execution.status}.",
                related_entity_type="Execution",
                related_entity_id=execution.id,
                evidence={
                    "status": execution.status,
                    "filled_quantity": float(execution.filled_quantity),
                    "remaining_quantity": float(execution.remaining_quantity),
                    "fill_notional": float(execution.fill_notional),
                },
            )
        return closure_check(
            "paper_execution",
            "Paper Execution",
            "warn",
            f"Latest paper execution status is {execution.status}.",
            next_actions=["Resolve the paper execution status before final closure."],
            related_entity_type="Execution",
            related_entity_id=execution.id,
            evidence={"execution_mode": execution.execution_mode, "status": execution.status},
        )

    def _post_trade_review_check(self, execution: Execution | None, review: PostTradeReview | None) -> dict[str, Any]:
        if execution is None:
            return closure_check(
                "post_trade_review",
                "Post-Trade Review",
                "warn",
                "Post-trade review will be required after paper execution.",
                next_actions=["Complete the post-trade review after the paper execution record is created."],
            )
        if review is None:
            return closure_check(
                "post_trade_review",
                "Post-Trade Review",
                "block",
                "Execution exists without a linked post-trade review.",
                blockers=["Missing PostTradeReview for latest execution."],
                next_actions=["Create or repair the post-trade review record before closure."],
                related_entity_type="Execution",
                related_entity_id=execution.id,
            )
        if review.status == "completed":
            return closure_check(
                "post_trade_review",
                "Post-Trade Review",
                "ok",
                "Post-trade review is completed.",
                related_entity_type="PostTradeReview",
                related_entity_id=review.id,
                evidence={"status": review.status, "review_keys": sorted(review.review_json.keys())},
            )
        if review.status in {"pending", "in_progress", "draft"}:
            return closure_check(
                "post_trade_review",
                "Post-Trade Review",
                "warn",
                f"Post-trade review status is {review.status}.",
                next_actions=["Complete the structured post-trade review before final closure."],
                related_entity_type="PostTradeReview",
                related_entity_id=review.id,
                evidence={"status": review.status},
            )
        return closure_check(
            "post_trade_review",
            "Post-Trade Review",
            "block",
            f"Post-trade review status is {review.status}.",
            blockers=[f"PostTradeReview status is {review.status}."],
            next_actions=["Resolve the post-trade review status before final closure."],
            related_entity_type="PostTradeReview",
            related_entity_id=review.id,
            evidence={"status": review.status},
        )

    def _safety_boundary_check(self, execution: Execution | None) -> dict[str, Any]:
        if execution is not None and execution.execution_mode != "paper":
            return closure_check(
                "safety_boundary",
                "Safety Boundary",
                "block",
                "Non-paper execution record detected in a paper-only closure report.",
                blockers=["Paper-only closure boundary was violated."],
                next_actions=["Escalate to live-execution reconciliation before continuing."],
                related_entity_type="Execution",
                related_entity_id=execution.id,
                evidence={"execution_available": False, "execution_mode": execution.execution_mode},
            )
        return closure_check(
            "safety_boundary",
            "Safety Boundary",
            "ok",
            "Closure report is read-only and does not expose execution controls.",
            evidence={"execution_available": False, "accepted_execution_modes": ["none", "paper"]},
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

    def _latest_approval(self, order_draft_id: str) -> Approval | None:
        return self.db.scalar(
            select(Approval)
            .where(Approval.order_draft_id == order_draft_id)
            .order_by(Approval.created_at.desc(), Approval.id.desc())
            .limit(1)
        )

    def _latest_execution(self, order_draft_id: str) -> Execution | None:
        return self.db.scalar(
            select(Execution)
            .where(Execution.order_draft_id == order_draft_id)
            .order_by(Execution.created_at.desc(), Execution.id.desc())
            .limit(1)
        )

    def _latest_review(self, order_draft_id: str) -> PostTradeReview | None:
        return self.db.scalar(
            select(PostTradeReview)
            .where(PostTradeReview.order_draft_id == order_draft_id)
            .order_by(PostTradeReview.updated_at.desc(), PostTradeReview.id.desc())
            .limit(1)
        )

    def _title(self, intent: OrderIntent | None, asset: Asset | None, draft: OrderDraft) -> str:
        symbol = asset.symbol if asset is not None else (intent.asset_id if intent is not None else draft.order_intent_id)
        return f"Order closure for {symbol}"

    def _detail(self, status: str, checks: list[dict[str, Any]]) -> str:
        blocked = sum(1 for item in checks if item["status"] == "block")
        warnings = sum(1 for item in checks if item["status"] == "warn")
        if status == "blocked":
            return f"{blocked} closure checks are blocking this order workflow."
        if status == "review_required":
            return f"{warnings} closure checks require human review before final closure."
        return "Order workflow has rationale, gates, risk, approval, paper execution, and completed post-trade review."


def closure_check(
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


def closure_rank(status: str) -> int:
    return {"blocked": 0, "review_required": 1, "closed": 2}.get(status, 1)


def quality_item(item: dict[str, Any]) -> dict[str, Any]:
    checks = item["checks"]
    ok_count = sum(1 for check in checks if check["status"] == "ok")
    warn_count = sum(1 for check in checks if check["status"] == "warn")
    block_count = sum(1 for check in checks if check["status"] == "block")
    quality_score = max(0.0, (ok_count - block_count) / len(checks)) if checks else 0.0
    hard_gaps = [f"{item['order_draft_id']}:{blocker}" for blocker in item["blockers"]]
    explanation_gaps = [
        f"{item['order_draft_id']}:{check['stage_key']}"
        for check in checks
        if check["status"] == "warn"
    ]
    return {
        "id": f"review-quality:{item['order_draft_id']}",
        "status": item["status"],
        "title": item["title"],
        "asset_id": item["asset_id"],
        "asset_symbol": item["asset_symbol"],
        "order_intent_id": item["order_intent_id"],
        "order_draft_id": item["order_draft_id"],
        "thesis_id": item["thesis_id"],
        "execution_id": item["execution_id"],
        "post_trade_review_id": item["post_trade_review_id"],
        "quality_score": round(quality_score, 4),
        "ok_count": ok_count,
        "warn_count": warn_count,
        "block_count": block_count,
        "hard_gaps": hard_gaps,
        "explanation_gaps": explanation_gaps,
        "next_actions": item["next_actions"],
        "execution_available": False,
    }


def review_action_item(
    *,
    item: dict[str, Any],
    gap_type: str,
    priority: str,
    gap: str,
    suggested_action: str,
) -> dict[str, Any]:
    return {
        "id": f"{item['order_draft_id']}:{gap_type}:{abs(hash(gap))}",
        "order_draft_id": item["order_draft_id"],
        "asset_symbol": item["asset_symbol"],
        "gap_type": gap_type,
        "priority": priority,
        "gap": gap,
        "suggested_action": suggested_action,
        "execution_available": False,
    }
