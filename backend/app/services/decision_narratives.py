from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account
from app.models import Approval
from app.models import Asset
from app.models import DecisionGate
from app.models import Execution
from app.models import InvestmentThesis
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import PlaybookUpdateProposal
from app.models import PostTradeReview
from app.models import RiskCheck
from app.models import Signal
from app.models import StrategyPlaybook


REQUIRED_GATE_TYPES = [
    "RESEARCH_GATE",
    "THESIS_GATE",
    "RISK_GATE",
    "BEHAVIOR_GATE",
    "EXECUTION_GATE",
]


class DecisionNarrativeNotFoundError(ValueError):
    pass


class DecisionNarrativeService:
    def __init__(self, db: Session):
        self.db = db

    def get_order_draft_narrative(self, draft_id: str) -> dict[str, Any]:
        draft = self.db.get(OrderDraft, draft_id)
        if draft is None:
            raise DecisionNarrativeNotFoundError("order draft not found")

        intent = self.db.get(OrderIntent, draft.order_intent_id)
        if intent is None:
            raise DecisionNarrativeNotFoundError("order intent not found")

        asset = self.db.get(Asset, intent.asset_id)
        account = self.db.get(Account, intent.account_id)
        thesis, thesis_link_kind = self._resolve_thesis(intent)
        playbook = self.db.get(StrategyPlaybook, intent.strategy_playbook_id) if intent.strategy_playbook_id else None
        signal = self._resolve_signal(intent)
        risk_checks = self._risk_checks(intent.id)
        gates = self._decision_gates(intent.id)
        approvals = self._approvals(draft.id)
        executions = self._executions(draft.id)
        reviews = self._post_trade_reviews(draft.id)
        proposals = self._playbook_proposals(reviews)

        sections = [
            self._source_signal_section(signal, intent, asset),
            self._thesis_section(thesis, thesis_link_kind, intent, playbook),
            self._gate_section(gates, risk_checks),
            self._order_section(draft, intent, account),
            self._post_trade_learning_section(executions, reviews),
            self._playbook_next_section(reviews, proposals, playbook),
        ]
        next_actions = self._next_actions(
            thesis=thesis,
            thesis_link_kind=thesis_link_kind,
            gates=gates,
            draft=draft,
            approvals=approvals,
            executions=executions,
            reviews=reviews,
            proposals=proposals,
        )
        safety_flags = self._safety_flags(draft, account, thesis, gates, executions, reviews)

        return {
            "draft_id": draft.id,
            "order_intent_id": intent.id,
            "asset_id": intent.asset_id,
            "asset_symbol": asset.symbol if asset is not None else None,
            "account_id": intent.account_id,
            "thesis_id": thesis.id if thesis is not None else None,
            "thesis_link_kind": thesis_link_kind,
            "signal_id": signal.id if signal is not None else None,
            "strategy_playbook_id": playbook.id if playbook is not None else intent.strategy_playbook_id,
            "current_stage": self._current_stage(draft, approvals, executions, reviews, proposals),
            "sections": sections,
            "timeline": self._timeline(intent, draft, risk_checks, gates, approvals, executions, reviews, proposals),
            "safety_flags": safety_flags,
            "next_actions": next_actions,
        }

    def _resolve_thesis(self, intent: OrderIntent) -> tuple[InvestmentThesis | None, str]:
        if intent.investment_thesis_id:
            thesis = self.db.get(InvestmentThesis, intent.investment_thesis_id)
            if thesis is not None:
                return thesis, "explicit"

        candidate = self.db.scalar(
            select(InvestmentThesis)
            .where(
                InvestmentThesis.asset_id == intent.asset_id,
                InvestmentThesis.status.in_(["active", "monitoring"]),
            )
            .order_by(InvestmentThesis.updated_at.desc(), InvestmentThesis.id.desc())
            .limit(1)
        )
        if candidate is not None:
            return candidate, "candidate_latest_active"
        return None, "missing"

    def _resolve_signal(self, intent: OrderIntent) -> Signal | None:
        if intent.source_signal_id:
            signal = self.db.get(Signal, intent.source_signal_id)
            if signal is not None:
                return signal
        if intent.source_type == "signal" and intent.source_id:
            return self.db.get(Signal, intent.source_id)
        return None

    def _risk_checks(self, order_intent_id: str) -> list[RiskCheck]:
        return list(
            self.db.scalars(
                select(RiskCheck)
                .where(RiskCheck.order_intent_id == order_intent_id)
                .order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc())
            ).all()
        )

    def _decision_gates(self, order_intent_id: str) -> list[DecisionGate]:
        return list(
            self.db.scalars(
                select(DecisionGate)
                .where(DecisionGate.order_intent_id == order_intent_id)
                .order_by(DecisionGate.created_at.desc(), DecisionGate.id.desc())
            ).all()
        )

    def _approvals(self, draft_id: str) -> list[Approval]:
        return list(
            self.db.scalars(
                select(Approval)
                .where(Approval.order_draft_id == draft_id)
                .order_by(Approval.created_at.desc(), Approval.id.desc())
            ).all()
        )

    def _executions(self, draft_id: str) -> list[Execution]:
        return list(
            self.db.scalars(
                select(Execution)
                .where(Execution.order_draft_id == draft_id)
                .order_by(Execution.created_at.desc(), Execution.id.desc())
            ).all()
        )

    def _post_trade_reviews(self, draft_id: str) -> list[PostTradeReview]:
        return list(
            self.db.scalars(
                select(PostTradeReview)
                .where(PostTradeReview.order_draft_id == draft_id)
                .order_by(PostTradeReview.created_at.desc(), PostTradeReview.id.desc())
            ).all()
        )

    def _playbook_proposals(self, reviews: list[PostTradeReview]) -> list[PlaybookUpdateProposal]:
        review_ids = [review.id for review in reviews]
        if not review_ids:
            return []
        return list(
            self.db.scalars(
                select(PlaybookUpdateProposal)
                .where(
                    PlaybookUpdateProposal.source_type == "post_trade_review",
                    PlaybookUpdateProposal.source_id.in_(review_ids),
                )
                .order_by(PlaybookUpdateProposal.created_at.desc(), PlaybookUpdateProposal.id.desc())
            ).all()
        )

    def _source_signal_section(self, signal: Signal | None, intent: OrderIntent, asset: Asset | None) -> dict[str, Any]:
        if signal is None:
            return section(
                "source_signal",
                "Source signal",
                "manual_source",
                "This draft was not sourced from a recorded signal; it must rely on manual rationale.",
                {
                    "source_type": intent.source_type,
                    "source_id": intent.source_id,
                    "asset_symbol": asset.symbol if asset is not None else None,
                },
                "Confirm that the manual rationale is explicit before approval.",
            )

        evidence = signal.evidence if isinstance(signal.evidence, dict) else {}
        input_context = as_record(evidence.get("input"))
        summary = (
            f"{asset.symbol if asset is not None else 'Asset'} {signal.signal_type} signal is "
            f"{signal.direction}: strength {as_float(signal.strength):.1f}/100, "
            f"confidence {as_float(signal.confidence):.2f}, suggested action {signal.suggested_action}."
        )
        return section(
            "source_signal",
            "Source signal",
            "needs_review" if signal.suggested_action.startswith("draft_") or signal.suggested_action == "reduce" else "watch_only",
            summary,
            {
                "signal_id": signal.id,
                "signal_type": signal.signal_type,
                "direction": signal.direction,
                "horizon": signal.horizon,
                "input_source": input_context.get("source"),
                "input_timeframe": input_context.get("timeframe"),
                "input_candle_count": input_context.get("candle_count", 0),
                "invalidation_condition": signal.invalidation_condition,
                "evidence_keys": sorted(evidence.keys()),
            },
            "Review the signal against thesis, risk, behavior, and execution gates before approval.",
        )

    def _thesis_section(
        self,
        thesis: InvestmentThesis | None,
        link_kind: str,
        intent: OrderIntent,
        playbook: StrategyPlaybook | None,
    ) -> dict[str, Any]:
        if thesis is None:
            has_user_rationale = bool(intent.user_rationale or intent.rationale)
            return section(
                "thesis_alignment",
                "Thesis alignment",
                "warning" if has_user_rationale else "blocked",
                "No linked or active thesis was found for this order intent.",
                {
                    "investment_thesis_id": intent.investment_thesis_id,
                    "user_rationale_present": has_user_rationale,
                    "strategy_playbook_id": intent.strategy_playbook_id,
                },
                "Create or link an investment thesis before relying on this draft.",
            )

        status = "ok" if thesis.status in {"active", "monitoring"} and link_kind == "explicit" else "warning"
        if thesis.status not in {"active", "monitoring"}:
            status = "blocked"
        summary = thesis.entry_reason
        if link_kind == "candidate_latest_active":
            summary = "Latest active thesis is available but the order intent is not explicitly linked to it."
        return section(
            "thesis_alignment",
            "Thesis alignment",
            status,
            summary,
            {
                "thesis_id": thesis.id,
                "link_kind": link_kind,
                "status": thesis.status,
                "expected_horizon": thesis.expected_horizon,
                "confidence": as_float(thesis.confidence),
                "max_loss_tolerance_pct": as_float(thesis.max_loss_tolerance_pct),
                "target_condition": thesis.target_condition,
                "key_drivers": thesis.key_drivers_json,
                "invalidation_conditions": thesis.invalidation_conditions_json,
                "strategy_playbook_id": playbook.id if playbook is not None else thesis.strategy_playbook_id,
                "strategy_playbook_name": playbook.name if playbook is not None else None,
            },
            "Keep invalidation conditions visible through approval and review.",
        )

    def _gate_section(self, gates: list[DecisionGate], risk_checks: list[RiskCheck]) -> dict[str, Any]:
        latest_gates = latest_by_gate_type(gates)
        missing = [gate_type for gate_type in REQUIRED_GATE_TYPES if gate_type not in latest_gates]
        gate_rows = [gate_evidence(latest_gates[gate_type]) for gate_type in REQUIRED_GATE_TYPES if gate_type in latest_gates]
        blocked = [row for row in gate_rows if row["status"] == "BLOCKED"]
        warnings = [row for row in gate_rows if row["status"] in {"WARNING", "HARD_CONFIRM_REQUIRED"}]
        latest_risk = risk_checks[0] if risk_checks else None

        if blocked or missing:
            status = "blocked"
        elif warnings:
            status = "warning"
        else:
            status = "ok"

        summary_parts = [f"{len(gate_rows)}/{len(REQUIRED_GATE_TYPES)} required gates recorded"]
        if blocked:
            summary_parts.append(f"{len(blocked)} blocked")
        if warnings:
            summary_parts.append(f"{len(warnings)} warning/confirmation")
        if latest_risk is not None:
            summary_parts.append(f"latest risk check is {latest_risk.status}")

        return section(
            "gate_summary",
            "Gate summary",
            status,
            "; ".join(summary_parts) + ".",
            {
                "required_gates": REQUIRED_GATE_TYPES,
                "missing_gates": missing,
                "latest_gates": gate_rows,
                "latest_risk_check": risk_evidence(latest_risk),
            },
            "Resolve missing or blocked gates before draft approval." if status == "blocked" else "Review warnings and keep gate evidence attached.",
        )

    def _order_section(self, draft: OrderDraft, intent: OrderIntent, account: Account | None) -> dict[str, Any]:
        if draft.approval_status == "rejected":
            status = "blocked"
        elif draft.approval_status in {"approved"}:
            status = "ok"
        elif draft.approval_status in {"pending", "modified"}:
            status = "warning"
        else:
            status = "pending"
        return section(
            "order_rationale",
            "Order rationale",
            status,
            intent.rationale,
            {
                "side": intent.side,
                "order_type": intent.order_type,
                "quantity": as_float(intent.quantity),
                "notional": as_float(intent.notional),
                "limit_price": as_float(intent.limit_price),
                "account_mode": account.mode if account is not None else None,
                "approval_status": draft.approval_status,
                "execution_status": draft.execution_status,
                "user_rationale": intent.user_rationale,
            },
            "Human approval can only move this to paper execution; live execution is not available here.",
        )

    def _post_trade_learning_section(self, executions: list[Execution], reviews: list[PostTradeReview]) -> dict[str, Any]:
        completed_reviews = [review for review in reviews if review.status == "completed"]
        if completed_reviews:
            review = completed_reviews[0]
            lesson = review_lesson(review)
            return section(
                "post_trade_learning",
                "Post-trade learning",
                "ok",
                lesson or "Post-trade review is completed.",
                {
                    "review_id": review.id,
                    "status": review.status,
                    "review_json": review.review_json,
                },
                "Use this lesson to decide whether the playbook needs a manual rule update.",
            )

        if reviews:
            review = reviews[0]
            return section(
                "post_trade_learning",
                "Post-trade learning",
                "warning",
                "Paper execution has a pending post-trade review.",
                {
                    "review_id": review.id,
                    "status": review.status,
                    "first_question": first_prompt_question(review),
                },
                "Complete the post-trade review before updating the playbook.",
            )

        if executions:
            return section(
                "post_trade_learning",
                "Post-trade learning",
                "warning",
                "Paper execution exists, but no post-trade review was found.",
                {"execution_ids": [execution.id for execution in executions]},
                "Create or restore the post-trade review record.",
            )

        return section(
            "post_trade_learning",
            "Post-trade learning",
            "pending",
            "No paper execution or post-trade review exists yet.",
            {},
            "After a paper fill, complete the review before changing rules.",
        )

    def _playbook_next_section(
        self,
        reviews: list[PostTradeReview],
        proposals: list[PlaybookUpdateProposal],
        playbook: StrategyPlaybook | None,
    ) -> dict[str, Any]:
        if proposals:
            proposal = proposals[0]
            status = "ok" if proposal.status in {"applied_manually", "published_as_new_version"} else "warning"
            return section(
                "playbook_next",
                "Playbook next",
                status,
                proposal.rationale,
                {
                    "proposal_id": proposal.id,
                    "proposal_status": proposal.status,
                    "requires_user_approval": proposal.requires_user_approval,
                    "strategy_playbook_id": proposal.strategy_playbook_id,
                    "playbook_name": playbook.name if playbook is not None else None,
                    "safe_apply_mode": proposal.proposal_json.get("safe_apply_mode"),
                    "auto_applied": False,
                },
                "Approve, reject, or apply the proposal manually; never auto-apply review lessons.",
            )

        if any(review.status == "completed" for review in reviews):
            return section(
                "playbook_next",
                "Playbook next",
                "warning",
                "A completed review exists, but no playbook update proposal has been created.",
                {"playbook_id": playbook.id if playbook is not None else None},
                "Create a manual playbook proposal if the lesson should become a rule.",
            )

        return section(
            "playbook_next",
            "Playbook next",
            "pending",
            "Playbook update is waiting for completed review evidence.",
            {"playbook_id": playbook.id if playbook is not None else None},
            "Do not change the playbook until the review is complete.",
        )

    def _next_actions(
        self,
        *,
        thesis: InvestmentThesis | None,
        thesis_link_kind: str,
        gates: list[DecisionGate],
        draft: OrderDraft,
        approvals: list[Approval],
        executions: list[Execution],
        reviews: list[PostTradeReview],
        proposals: list[PlaybookUpdateProposal],
    ) -> list[str]:
        actions: list[str] = []
        latest_gates = latest_by_gate_type(gates)
        if thesis is None:
            actions.append("Create or link an investment thesis before relying on this draft.")
        elif thesis_link_kind != "explicit":
            actions.append("Attach the candidate thesis explicitly to the order intent for auditability.")

        missing_gates = [gate_type for gate_type in REQUIRED_GATE_TYPES if gate_type not in latest_gates]
        blocked_gates = [gate for gate in latest_gates.values() if gate.status == "BLOCKED"]
        if missing_gates or blocked_gates:
            actions.append("Resolve missing or blocked decision gates before approval.")

        if draft.approval_status == "pending":
            actions.append("Human reviewer should approve, reject, or request modification.")
        elif draft.approval_status == "approved" and not executions:
            actions.append("Use paper execution only; live execution remains unavailable.")
        elif approvals and approvals[0].status == "rejected":
            actions.append("Keep the rejected draft in audit history and create a new intent if needed.")

        if executions and not any(review.status == "completed" for review in reviews):
            actions.append("Complete the post-trade review before learning from the trade.")
        if any(review.status == "completed" for review in reviews) and not proposals:
            actions.append("Create a manual playbook update proposal if the lesson should become a rule.")
        if any(proposal.status == "pending" for proposal in proposals):
            actions.append("Review the pending playbook proposal; approve, reject, or keep pending.")
        if any(proposal.status == "approved_pending_manual_apply" for proposal in proposals):
            actions.append("Preview and apply the approved proposal manually before publishing a new playbook version.")

        if not actions:
            actions.append("Continue monitoring thesis health and later outcomes.")
        return actions

    def _safety_flags(
        self,
        draft: OrderDraft,
        account: Account | None,
        thesis: InvestmentThesis | None,
        gates: list[DecisionGate],
        executions: list[Execution],
        reviews: list[PostTradeReview],
    ) -> dict[str, Any]:
        latest_gates = latest_by_gate_type(gates)
        all_gates_passed = bool(latest_gates) and all(
            gate_type in latest_gates and latest_gates[gate_type].status == "PASSED"
            for gate_type in REQUIRED_GATE_TYPES
        )
        return {
            "live_execution_available": False,
            "broker_execution_called": False,
            "exchange_execution_called": False,
            "wallet_write_called": False,
            "approval_required": True,
            "account_mode": account.mode if account is not None else None,
            "account_live_trading_enabled": bool(account.live_trading_enabled) if account is not None else False,
            "paper_execution_available": bool(account is not None and account.mode == "paper" and draft.approval_status == "approved"),
            "fail_closed_on_missing_thesis": thesis is None,
            "fail_closed_on_missing_gates": not all_gates_passed,
            "all_latest_gates_passed": all_gates_passed,
            "paper_executions_count": len(executions),
            "completed_reviews_count": len([review for review in reviews if review.status == "completed"]),
        }

    def _current_stage(
        self,
        draft: OrderDraft,
        approvals: list[Approval],
        executions: list[Execution],
        reviews: list[PostTradeReview],
        proposals: list[PlaybookUpdateProposal],
    ) -> str:
        if any(proposal.status in {"applied_manually", "published_as_new_version"} for proposal in proposals):
            return "playbook_updated"
        if any(review.status == "completed" for review in reviews):
            return "post_trade_reviewed"
        if reviews:
            return "review_scheduled"
        if executions:
            return "paper_executed"
        if any(approval.status == "approved" for approval in approvals):
            return "approved"
        if any(approval.status == "rejected" for approval in approvals):
            return "rejected"
        if draft.approval_status == "pending":
            return "approval_required"
        return "order_draft_created"

    def _timeline(
        self,
        intent: OrderIntent,
        draft: OrderDraft,
        risk_checks: list[RiskCheck],
        gates: list[DecisionGate],
        approvals: list[Approval],
        executions: list[Execution],
        reviews: list[PostTradeReview],
        proposals: list[PlaybookUpdateProposal],
    ) -> list[dict[str, Any]]:
        events = [
            event(f"intent:{intent.id}", "OrderIntent", intent.status, intent.rationale, intent.created_at),
            event(
                f"draft:{draft.id}",
                "OrderDraft",
                draft.approval_status,
                f"risk={draft.risk_status}; behavior={draft.behavior_status}; execution={draft.execution_status}",
                draft.created_at,
            ),
        ]
        events.extend(
            event(f"risk:{risk.id}", "RiskCheck", risk.status, risk.reason or "Risk rules evaluated.", risk.created_at)
            for risk in risk_checks
        )
        events.extend(
            event(
                f"gate:{gate.id}",
                gate.gate_type,
                gate.status,
                " ; ".join([*gate.blocking_reasons_json, *gate.warnings_json]) or gate.recommended_intervention_level,
                gate.created_at,
            )
            for gate in gates
        )
        events.extend(
            event(
                f"approval:{approval.id}",
                "Approval",
                approval.status,
                approval.decision_reason or "Approval decision recorded.",
                approval.decided_at or approval.created_at,
            )
            for approval in approvals
        )
        events.extend(
            event(
                f"paper:{execution.id}",
                "PaperExecution",
                execution.status,
                f"filled={as_float(execution.filled_quantity)}; pnl={as_float(execution.realized_pnl)}",
                execution.created_at,
            )
            for execution in executions
        )
        events.extend(
            event(
                f"review:{review.id}",
                "PostTradeReview",
                review.status,
                review_lesson(review) or first_prompt_question(review) or "Review prompt created.",
                review.updated_at,
            )
            for review in reviews
        )
        events.extend(
            event(
                f"proposal:{proposal.id}",
                "PlaybookProposal",
                proposal.status,
                proposal.rationale,
                proposal.reviewed_at or proposal.created_at,
            )
            for proposal in proposals
        )
        return sorted(events, key=lambda item: item["created_at"])


def section(
    key: str,
    title: str,
    status: str,
    summary: str,
    evidence: dict[str, Any],
    next_action: str | None,
) -> dict[str, Any]:
    return {
        "key": key,
        "title": title,
        "status": status,
        "summary": summary,
        "evidence": evidence,
        "next_action": next_action,
    }


def event(id_: str, label: str, status: str, detail: str, created_at: datetime) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "status": status,
        "detail": detail,
        "created_at": created_at,
    }


def latest_by_gate_type(gates: list[DecisionGate]) -> dict[str, DecisionGate]:
    latest: dict[str, DecisionGate] = {}
    for gate in gates:
        if gate.gate_type not in latest:
            latest[gate.gate_type] = gate
    return latest


def gate_evidence(gate: DecisionGate) -> dict[str, Any]:
    return {
        "gate_type": gate.gate_type,
        "status": gate.status,
        "score": as_float(gate.score),
        "blocking_reasons": gate.blocking_reasons_json,
        "warnings": gate.warnings_json,
        "recommended_intervention_level": gate.recommended_intervention_level,
        "evaluator": gate.evaluator,
        "created_at": gate.created_at.isoformat(),
    }


def risk_evidence(risk_check: RiskCheck | None) -> dict[str, Any] | None:
    if risk_check is None:
        return None
    failed_rules: list[str] = []
    rules = as_record(risk_check.rules_json).get("rules")
    if isinstance(rules, list):
        for item in rules:
            row = as_record(item)
            if row and not bool(row.get("passed")):
                failed_rules.append(str(row.get("rule", "unknown_rule")))
    return {
        "id": risk_check.id,
        "status": risk_check.status,
        "hard_rule_passed": risk_check.hard_rule_passed,
        "failed_rules": failed_rules,
        "reason": risk_check.reason,
        "created_at": risk_check.created_at.isoformat(),
    }


def review_lesson(review: PostTradeReview) -> str:
    payload = as_record(review.review_json)
    for key in ["lesson", "lessons", "summary", "decision_quality", "what_to_change"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def first_prompt_question(review: PostTradeReview) -> str:
    questions = as_record(review.prompt_json).get("questions")
    if isinstance(questions, list) and questions:
        return str(questions[0])
    return ""


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
