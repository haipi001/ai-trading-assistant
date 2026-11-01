import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.providers import MockAIProvider
from app.models import Approval
from app.models import AuditLog
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import MonthlyDecisionReview
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import Position
from app.models import ThesisViolation


IMPULSIVE_PATTERN_TYPES = {
    "FOMO_BUYING",
    "PANIC_SELLING",
    "OVERTRADING",
    "REVENGE_TRADING",
    "AVERAGING_DOWN_AFTER_LOSSES",
    "SELLING_WINNERS_TOO_EARLY",
    "HOLDING_LOSERS_TOO_LONG",
    "THESIS_CONFLICT_TRADE",
    "SOCIAL_MEDIA_TRIGGERED_TRADE",
}

BLOCKING_INTERVENTION_LEVELS = {"BLOCK"}
WARNING_INTERVENTION_LEVELS = {"SOFT_WARNING", "HARD_CONFIRM"}


@dataclass(frozen=True)
class MonthlyReviewResult:
    review: MonthlyDecisionReview
    metrics: dict[str, Any]
    behavior_summary: str
    decision_quality_summary: str
    recommended_constitution_updates: list[dict[str, Any]]
    recommended_playbook_updates: list[dict[str, Any]]
    most_common_behavior_pattern: str | None
    biggest_prevented_loss: float
    automatic_rule_updates_applied: bool = False


class MonthlyDecisionReviewService:
    def __init__(self, db: Session, ai_provider: MockAIProvider | None = None) -> None:
        self.db = db
        self.ai_provider = ai_provider or MockAIProvider()

    def generate(self, *, user_id: str, period_start: date, period_end: date) -> MonthlyReviewResult:
        start_at, end_before = self._period_bounds(period_start, period_end)
        order_intents = self._order_intents(start_at, end_before)
        intent_ids = {intent.id for intent in order_intents}

        interventions = self._interventions(user_id, start_at, end_before)
        patterns = self._patterns(user_id, start_at, end_before)
        violations = self._violations(user_id, start_at, end_before)
        drafts = self._drafts(intent_ids, start_at, end_before)
        approvals = self._approvals({draft.id for draft in drafts}, start_at, end_before)

        pattern_by_id = {pattern.id: pattern for pattern in patterns}
        impulsive_intent_ids = self._impulsive_intent_ids(interventions, pattern_by_id)
        violating_intent_ids = {violation.related_order_intent_id for violation in violations if violation.related_order_intent_id}
        blocked_intent_ids = self._blocked_intent_ids(order_intents, interventions, drafts, approvals)

        total_trades = len(order_intents)
        thesis_violating_trades = len(violating_intent_ids) if violating_intent_ids else len(violations)
        impulsive_trades = len(impulsive_intent_ids)
        thesis_aligned_trades = sum(
            1
            for intent in order_intents
            if intent.investment_thesis_id
            and intent.id not in violating_intent_ids
            and intent.id not in impulsive_intent_ids
        )
        planned_trades = max(total_trades - impulsive_trades, 0)
        blocked_trades = len(blocked_intent_ids)
        bypassed_warnings = sum(
            1
            for intervention in interventions
            if intervention.bypassed and intervention.intervention_level in WARNING_INTERVENTION_LEVELS
        )

        planned_trade_pnl, impulsive_trade_pnl = self._attribute_pnl(order_intents, impulsive_intent_ids)
        overtrading_cost = self._overtrading_cost(patterns)
        top_behavior_patterns = self._top_behavior_patterns(interventions, pattern_by_id, patterns)
        most_common_behavior_pattern = top_behavior_patterns[0]["pattern_type"] if top_behavior_patterns else None
        biggest_prevented_loss = self._biggest_prevented_loss(interventions, pattern_by_id)

        metrics = {
            "total_trades": total_trades,
            "thesis_aligned_trades": thesis_aligned_trades,
            "thesis_violating_trades": thesis_violating_trades,
            "impulsive_trades": impulsive_trades,
            "planned_trades": planned_trades,
            "blocked_trades": blocked_trades,
            "warnings_bypassed": bypassed_warnings,
            "planned_trade_pnl": planned_trade_pnl,
            "impulsive_trade_pnl": impulsive_trade_pnl,
            "overtrading_cost": overtrading_cost,
            "most_common_behavior_pattern": most_common_behavior_pattern,
            "biggest_prevented_loss": biggest_prevented_loss,
        }
        behavior_summary = self._behavior_summary(metrics)
        decision_quality_summary = self._decision_quality_summary(metrics)
        constitution_updates = self._recommended_constitution_updates(metrics)
        playbook_updates = self._recommended_playbook_updates(metrics)
        recommended_updates = constitution_updates + playbook_updates
        ai_summary = self._ai_summary(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            metrics=metrics,
            behavior_summary=behavior_summary,
            decision_quality_summary=decision_quality_summary,
        )

        review = MonthlyDecisionReview(
            user_id=user_id,
            period_start=period_start,
            period_end=period_end,
            total_trades=total_trades,
            thesis_aligned_trades=thesis_aligned_trades,
            thesis_violating_trades=thesis_violating_trades,
            impulsive_trades=impulsive_trades,
            blocked_trades=blocked_trades,
            bypassed_warnings=bypassed_warnings,
            planned_trade_pnl=planned_trade_pnl,
            impulsive_trade_pnl=impulsive_trade_pnl,
            overtrading_cost=overtrading_cost,
            top_behavior_patterns_json=top_behavior_patterns,
            recommended_rule_updates_json=recommended_updates,
            ai_summary=ai_summary,
        )
        self.db.add(review)
        self.db.flush()
        self._write_audit_log(review, metrics)
        self.db.commit()
        self.db.refresh(review)

        return MonthlyReviewResult(
            review=review,
            metrics=metrics,
            behavior_summary=behavior_summary,
            decision_quality_summary=decision_quality_summary,
            recommended_constitution_updates=constitution_updates,
            recommended_playbook_updates=playbook_updates,
            most_common_behavior_pattern=most_common_behavior_pattern,
            biggest_prevented_loss=biggest_prevented_loss,
        )

    def quarterly_trend(self, *, user_id: str, months: int = 3) -> dict[str, Any]:
        review_limit = max(1, min(months, 12))
        reviews = list(
            self.db.scalars(
                select(MonthlyDecisionReview)
                .where(MonthlyDecisionReview.user_id == user_id)
                .order_by(MonthlyDecisionReview.period_start.desc(), MonthlyDecisionReview.created_at.desc())
                .limit(review_limit)
            ).all()
        )
        chronological = list(reversed(reviews))
        totals = {
            "total_trades": sum(review.total_trades for review in reviews),
            "thesis_aligned_trades": sum(review.thesis_aligned_trades for review in reviews),
            "thesis_violating_trades": sum(review.thesis_violating_trades for review in reviews),
            "impulsive_trades": sum(review.impulsive_trades for review in reviews),
            "blocked_trades": sum(review.blocked_trades for review in reviews),
            "bypassed_warnings": sum(review.bypassed_warnings for review in reviews),
            "planned_trade_pnl": sum(self._to_float(review.planned_trade_pnl) for review in reviews),
            "impulsive_trade_pnl": sum(self._to_float(review.impulsive_trade_pnl) for review in reviews),
            "overtrading_cost": sum(self._to_float(review.overtrading_cost) for review in reviews),
        }
        pattern_counter: Counter[str] = Counter()
        rule_counter: Counter[str] = Counter()
        for review in reviews:
            for pattern in review.top_behavior_patterns_json or []:
                pattern_counter[str(pattern.get("pattern_type") or pattern.get("type") or "UNKNOWN")] += int(pattern.get("count") or pattern.get("frequency") or 1)
            for rule in review.recommended_rule_updates_json or []:
                rule_counter[str(rule.get("update_type") or rule.get("type") or rule.get("target") or "rule_update")] += 1

        first = chronological[0] if chronological else None
        last = chronological[-1] if chronological else None
        trend = {
            "impulsive_trades": self._trend_direction(first.impulsive_trades if first else 0, last.impulsive_trades if last else 0),
            "thesis_violations": self._trend_direction(first.thesis_violating_trades if first else 0, last.thesis_violating_trades if last else 0),
            "blocked_trades": self._trend_direction(first.blocked_trades if first else 0, last.blocked_trades if last else 0),
            "planned_pnl": self._trend_direction(self._to_float(first.planned_trade_pnl) if first else 0, self._to_float(last.planned_trade_pnl) if last else 0, higher_is_better=True),
        }
        review_rows = [
            {
                "id": review.id,
                "period_start": review.period_start.isoformat(),
                "period_end": review.period_end.isoformat(),
                "total_trades": review.total_trades,
                "thesis_aligned_trades": review.thesis_aligned_trades,
                "thesis_violating_trades": review.thesis_violating_trades,
                "impulsive_trades": review.impulsive_trades,
                "blocked_trades": review.blocked_trades,
                "bypassed_warnings": review.bypassed_warnings,
                "planned_trade_pnl": self._to_float(review.planned_trade_pnl),
                "impulsive_trade_pnl": self._to_float(review.impulsive_trade_pnl),
            }
            for review in chronological
        ]
        blockers: list[str] = []
        if not reviews:
            blockers.append("monthly_reviews_missing")
        elif len(reviews) < review_limit:
            blockers.append("insufficient_review_history")
        status = "blocked" if not reviews else ("review_required" if blockers else "ready")
        insight = self._quarterly_insight(totals, pattern_counter, trend, len(reviews))
        return {
            "user_id": user_id,
            "status": status,
            "window_months": review_limit,
            "review_count": len(reviews),
            "period_start": chronological[0].period_start.isoformat() if chronological else None,
            "period_end": chronological[-1].period_end.isoformat() if chronological else None,
            "totals": totals,
            "trend": trend,
            "top_behavior_patterns": [{"pattern_type": name, "count": count} for name, count in pattern_counter.most_common(5)],
            "recommended_rule_updates": [{"update_type": name, "count": count, "requires_user_approval": True} for name, count in rule_counter.most_common(5)],
            "reviews": review_rows,
            "insight": insight,
            "blockers": blockers,
            "next_actions": self._quarterly_next_actions(status, totals, pattern_counter),
            "execution_available": False,
            "automatic_rule_updates_applied": False,
            "review_only": True,
        }

    def _period_bounds(self, period_start: date, period_end: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(period_start, time.min, tzinfo=timezone.utc),
            datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=timezone.utc),
        )

    def _order_intents(self, start_at: datetime, end_before: datetime) -> list[OrderIntent]:
        return list(
            self.db.scalars(
                select(OrderIntent).where(OrderIntent.created_at >= start_at, OrderIntent.created_at < end_before)
            ).all()
        )

    def _interventions(self, user_id: str, start_at: datetime, end_before: datetime) -> list[BehaviorIntervention]:
        return list(
            self.db.scalars(
                select(BehaviorIntervention).where(
                    BehaviorIntervention.user_id == user_id,
                    BehaviorIntervention.created_at >= start_at,
                    BehaviorIntervention.created_at < end_before,
                )
            ).all()
        )

    def _patterns(self, user_id: str, start_at: datetime, end_before: datetime) -> list[BehaviorPattern]:
        return list(
            self.db.scalars(
                select(BehaviorPattern).where(
                    BehaviorPattern.user_id == user_id,
                    BehaviorPattern.created_at >= start_at,
                    BehaviorPattern.created_at < end_before,
                )
            ).all()
        )

    def _violations(self, user_id: str, start_at: datetime, end_before: datetime) -> list[ThesisViolation]:
        return list(
            self.db.scalars(
                select(ThesisViolation).where(
                    ThesisViolation.user_id == user_id,
                    ThesisViolation.created_at >= start_at,
                    ThesisViolation.created_at < end_before,
                )
            ).all()
        )

    def _drafts(self, intent_ids: set[str], start_at: datetime, end_before: datetime) -> list[OrderDraft]:
        if not intent_ids:
            return []
        return list(
            self.db.scalars(
                select(OrderDraft).where(
                    OrderDraft.order_intent_id.in_(intent_ids),
                    OrderDraft.created_at >= start_at,
                    OrderDraft.created_at < end_before,
                )
            ).all()
        )

    def _approvals(self, draft_ids: set[str], start_at: datetime, end_before: datetime) -> list[Approval]:
        if not draft_ids:
            return []
        return list(
            self.db.scalars(
                select(Approval).where(
                    Approval.order_draft_id.in_(draft_ids),
                    Approval.created_at >= start_at,
                    Approval.created_at < end_before,
                )
            ).all()
        )

    def _impulsive_intent_ids(
        self,
        interventions: list[BehaviorIntervention],
        pattern_by_id: dict[str, BehaviorPattern],
    ) -> set[str]:
        intent_ids: set[str] = set()
        for intervention in interventions:
            pattern = pattern_by_id.get(intervention.pattern_id or "")
            if pattern and pattern.pattern_type in IMPULSIVE_PATTERN_TYPES and intervention.order_intent_id:
                intent_ids.add(intervention.order_intent_id)
        return intent_ids

    def _blocked_intent_ids(
        self,
        order_intents: list[OrderIntent],
        interventions: list[BehaviorIntervention],
        drafts: list[OrderDraft],
        approvals: list[Approval],
    ) -> set[str]:
        intent_ids = {intent.id for intent in order_intents if intent.status in {"blocked", "rejected"}}
        draft_to_intent = {draft.id: draft.order_intent_id for draft in drafts}
        intent_ids.update(
            intervention.order_intent_id
            for intervention in interventions
            if intervention.order_intent_id and intervention.intervention_level in BLOCKING_INTERVENTION_LEVELS
        )
        intent_ids.update(
            draft.order_intent_id
            for draft in drafts
            if draft.risk_status == "blocked"
            or draft.behavior_status == "blocked"
            or draft.approval_status == "rejected"
        )
        intent_ids.update(
            draft_to_intent[approval.order_draft_id]
            for approval in approvals
            if approval.order_draft_id in draft_to_intent and approval.status == "rejected"
        )
        return intent_ids

    def _attribute_pnl(self, order_intents: list[OrderIntent], impulsive_intent_ids: set[str]) -> tuple[float, float]:
        planned_pnl = 0.0
        impulsive_pnl = 0.0
        seen_position_keys: set[tuple[str, str, bool]] = set()
        for intent in order_intents:
            is_impulsive = intent.id in impulsive_intent_ids
            position_key = (intent.account_id, intent.asset_id, is_impulsive)
            if position_key in seen_position_keys:
                continue
            position = self.db.scalar(
                select(Position).where(Position.account_id == intent.account_id, Position.asset_id == intent.asset_id)
            )
            if not position:
                continue
            pnl = self._to_float(position.realized_pnl) + self._to_float(position.unrealized_pnl)
            if is_impulsive:
                impulsive_pnl += pnl
            else:
                planned_pnl += pnl
            seen_position_keys.add(position_key)
        return planned_pnl, impulsive_pnl

    def _overtrading_cost(self, patterns: list[BehaviorPattern]) -> float:
        return sum(
            self._to_float(pattern.estimated_cost)
            for pattern in patterns
            if pattern.pattern_type in {"OVERTRADING", "REVENGE_TRADING"}
        )

    def _top_behavior_patterns(
        self,
        interventions: list[BehaviorIntervention],
        pattern_by_id: dict[str, BehaviorPattern],
        patterns: list[BehaviorPattern],
    ) -> list[dict[str, Any]]:
        counter: Counter[str] = Counter()
        for intervention in interventions:
            pattern = pattern_by_id.get(intervention.pattern_id or "")
            if pattern:
                counter[pattern.pattern_type] += 1
        for pattern in patterns:
            if pattern.frequency and pattern.pattern_type not in counter:
                counter[pattern.pattern_type] += pattern.frequency
        return [
            {"pattern_type": pattern_type, "count": count}
            for pattern_type, count in counter.most_common()
        ]

    def _biggest_prevented_loss(
        self,
        interventions: list[BehaviorIntervention],
        pattern_by_id: dict[str, BehaviorPattern],
    ) -> float:
        losses = []
        for intervention in interventions:
            if intervention.intervention_level != "BLOCK":
                continue
            pattern = pattern_by_id.get(intervention.pattern_id or "")
            if pattern:
                losses.append(self._to_float(pattern.estimated_cost))
        return max(losses, default=0.0)

    def _behavior_summary(self, metrics: dict[str, Any]) -> str:
        common = metrics["most_common_behavior_pattern"] or "none"
        return (
            f"Behavior review found {metrics['impulsive_trades']} impulsive trade attempts, "
            f"{metrics['warnings_bypassed']} bypassed warnings, and most common pattern: {common}."
        )

    def _decision_quality_summary(self, metrics: dict[str, Any]) -> str:
        return (
            f"Decision attribution: {metrics['planned_trades']} planned decisions vs "
            f"{metrics['impulsive_trades']} impulsive decisions; "
            f"{metrics['thesis_violating_trades']} thesis violations and {metrics['blocked_trades']} blocked attempts."
        )

    def _recommended_constitution_updates(self, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        if metrics["warnings_bypassed"] > 0:
            updates.append(
                self._rule_update(
                    target="InvestmentConstitution",
                    update_type="tighten_warning_bypass_policy",
                    rationale="Warnings were bypassed during the review period; consider requiring HARD_CONFIRM after repeated bypasses.",
                )
            )
        if metrics["blocked_trades"] > 0:
            updates.append(
                self._rule_update(
                    target="InvestmentConstitution",
                    update_type="review_blocking_thresholds",
                    rationale="Blocked trade attempts indicate constitution-level constraints were active and should be reviewed for clarity.",
                )
            )
        return updates

    def _recommended_playbook_updates(self, metrics: dict[str, Any]) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []
        if metrics["impulsive_trades"] > 0:
            updates.append(
                self._rule_update(
                    target="StrategyPlaybook",
                    update_type="add_pre_trade_cooldown_checklist",
                    rationale="Impulsive trade attempts were detected; add a pre-trade checklist and cooldown rule to relevant playbooks.",
                )
            )
        if metrics["thesis_violating_trades"] > 0:
            updates.append(
                self._rule_update(
                    target="StrategyPlaybook",
                    update_type="strengthen_thesis_invalidation_rules",
                    rationale="Thesis-violating actions occurred; playbooks should require explicit thesis invalidation evidence before exit actions.",
                )
            )
        return updates

    def _rule_update(self, *, target: str, update_type: str, rationale: str) -> dict[str, Any]:
        return {
            "target": target,
            "update_type": update_type,
            "rationale": rationale,
            "requires_user_approval": True,
            "automatic_update_applied": False,
        }

    def _ai_summary(
        self,
        *,
        user_id: str,
        period_start: date,
        period_end: date,
        metrics: dict[str, Any],
        behavior_summary: str,
        decision_quality_summary: str,
    ) -> str:
        report_json = self.ai_provider.generate_report(
            report_type="monthly_decision_review",
            agent_name="MockMonthlyDecisionReviewer",
            data_snapshot_id=f"monthly-review-{user_id}-{period_start.isoformat()}-{period_end.isoformat()}",
            input_facts={
                "metrics": metrics,
                "behavior_summary": behavior_summary,
                "decision_quality_summary": decision_quality_summary,
                "rule_update_policy": "suggestions_require_user_approval",
                "advice_boundary": "review_decision_quality_only_no_direct_investment_advice",
            },
            prompt_template="",
        )
        report = json.loads(report_json)
        return (
            f"{behavior_summary} {decision_quality_summary} "
            f"MockAIProvider commentary: {report['summary']} This is not direct investment advice."
        )

    def _write_audit_log(self, review: MonthlyDecisionReview, metrics: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="monthly-decision-review-service",
                action="monthly_decision_review.generated",
                entity_type="MonthlyDecisionReview",
                entity_id=review.id,
                payload_json={
                    "user_id": review.user_id,
                    "period_start": review.period_start.isoformat(),
                    "period_end": review.period_end.isoformat(),
                    "metrics": metrics,
                    "automatic_rule_updates_applied": False,
                    "execution_performed": False,
                },
            )
        )

    def _to_float(self, value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        return float(value)

    def _trend_direction(self, first: float | int, last: float | int, *, higher_is_better: bool = False) -> str:
        first_value = float(first)
        last_value = float(last)
        if abs(last_value - first_value) < 0.000001:
            return "flat"
        improved = last_value > first_value if higher_is_better else last_value < first_value
        return "improving" if improved else "worsening"

    def _quarterly_insight(self, totals: dict[str, Any], pattern_counter: Counter[str], trend: dict[str, str], review_count: int) -> str:
        if review_count == 0:
            return "No monthly reviews exist yet. Generate at least one monthly review before reading quarterly trends."
        common = pattern_counter.most_common(1)[0][0] if pattern_counter else "none"
        return (
            f"Quarterly review covers {review_count} monthly review(s), {totals['total_trades']} trade decisions, "
            f"{totals['impulsive_trades']} impulsive decisions, {totals['thesis_violating_trades']} thesis violations, "
            f"and {totals['blocked_trades']} blocked attempts. Most common behavior pattern: {common}. "
            f"Impulsive trend is {trend['impulsive_trades']}; planned PnL trend is {trend['planned_pnl']}. "
            "This is a review-only trend summary, not trading advice."
        )

    def _quarterly_next_actions(self, status: str, totals: dict[str, Any], pattern_counter: Counter[str]) -> list[str]:
        if status == "blocked":
            return ["Generate monthly reviews first, then revisit quarterly trend."]
        actions = ["Review the trend before changing any rule; rule updates still require human approval."]
        if totals["impulsive_trades"] > 0:
            actions.append("Add one concrete cooldown or pre-trade checklist item to the next Playbook review.")
        if totals["thesis_violating_trades"] > 0:
            actions.append("Review thesis invalidation conditions before creating new plans.")
        if pattern_counter:
            actions.append(f"Focus next month on reducing {pattern_counter.most_common(1)[0][0]}.")
        return actions
