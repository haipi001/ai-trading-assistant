from datetime import datetime
from datetime import timedelta
from datetime import timezone
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Asset
from app.models import AuditLog
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import InvestmentConstitution
from app.models import InvestmentThesis
from app.models import OrderIntent
from app.models import ThesisViolation


INTERVENTION_RANK = {
    "SILENT_RECORD": 0,
    "SOFT_WARNING": 1,
    "HARD_CONFIRM": 2,
    "BLOCK": 3,
}


PATTERN_DEFAULT_LEVEL = {
    "FOMO_BUYING": "HARD_CONFIRM",
    "PANIC_SELLING": "HARD_CONFIRM",
    "OVERTRADING": "SOFT_WARNING",
    "REVENGE_TRADING": "HARD_CONFIRM",
    "AVERAGING_DOWN_AFTER_LOSSES": "HARD_CONFIRM",
    "SELLING_WINNERS_TOO_EARLY": "SOFT_WARNING",
    "HOLDING_LOSERS_TOO_LONG": "SOFT_WARNING",
    "CONCENTRATION_DRIFT": "BLOCK",
    "THESIS_CONFLICT_TRADE": "HARD_CONFIRM",
    "SOCIAL_MEDIA_TRIGGERED_TRADE": "HARD_CONFIRM",
}


class BehaviorEvaluationError(ValueError):
    pass


class InterventionNotFoundError(ValueError):
    pass


@dataclass
class DetectedBehavior:
    pattern_type: str
    level: str
    evidence: dict[str, Any]
    description: str
    severity: str


@dataclass
class BehaviorEvaluationResult:
    order_intent_id: str
    patterns: list[BehaviorPattern]
    intervention: BehaviorIntervention
    level: str
    message: str
    evidence: dict[str, Any]
    required_user_action: str
    bypass_allowed: bool
    thesis_violation: ThesisViolation | None = None


class BehaviorEngine:
    def __init__(self, db: Session):
        self.db = db

    def evaluate_order(self, order_intent_id: str, context: dict[str, Any]) -> BehaviorEvaluationResult:
        order_intent = self.db.get(OrderIntent, order_intent_id)
        if order_intent is None:
            raise BehaviorEvaluationError("order intent not found")
        asset = self.db.get(Asset, order_intent.asset_id)
        if asset is None:
            raise BehaviorEvaluationError("order intent asset is unavailable")

        thesis = self.db.get(InvestmentThesis, order_intent.investment_thesis_id) if order_intent.investment_thesis_id else None
        user_id = self._resolve_user_id(order_intent, thesis, context)
        constitution = self._active_constitution(user_id)
        detections = self._detect_patterns(order_intent, asset, thesis, constitution, context)
        detections = self._escalate_detections(user_id, detections)
        if not detections:
            detections = [
                DetectedBehavior(
                    pattern_type="NO_BEHAVIOR_PATTERN_DETECTED",
                    level="SILENT_RECORD",
                    evidence={"reason": "No configured behavior pattern was detected."},
                    description="No configured behavior pattern was detected for this order intent.",
                    severity="low",
                )
            ]

        patterns = [self._store_pattern(user_id, asset.id, detection) for detection in detections]
        primary = max(detections, key=lambda detection: INTERVENTION_RANK[detection.level])
        primary_pattern = patterns[detections.index(primary)]
        thesis_violation = self._create_thesis_violation(order_intent, thesis, user_id, primary, context)
        message = self._message(order_intent, asset, thesis, primary, context)
        required_user_action = self._required_user_action(primary.level)
        bypass_allowed = primary.level != "BLOCK"
        intervention = self._store_intervention(
            user_id=user_id,
            pattern_id=primary_pattern.id if primary_pattern.pattern_type != "NO_BEHAVIOR_PATTERN_DETECTED" else None,
            order_intent_id=order_intent.id,
            level=primary.level,
            message=message,
        )
        self._write_audit_log(
            action="behavior_order.evaluated",
            entity_type="OrderIntent",
            entity_id=order_intent.id,
            payload_json={
                "user_id": user_id,
                "patterns": [detection.pattern_type for detection in detections],
                "intervention_id": intervention.id,
                "level": primary.level,
                "required_user_action": required_user_action,
                "bypass_allowed": bypass_allowed,
                "thesis_violation_id": thesis_violation.id if thesis_violation else None,
            },
        )
        self.db.commit()
        for pattern in patterns:
            self.db.refresh(pattern)
        self.db.refresh(intervention)
        if thesis_violation:
            self.db.refresh(thesis_violation)
        return BehaviorEvaluationResult(
            order_intent_id=order_intent.id,
            patterns=patterns,
            intervention=intervention,
            level=primary.level,
            message=message,
            evidence=self._combined_evidence(detections),
            required_user_action=required_user_action,
            bypass_allowed=bypass_allowed,
            thesis_violation=thesis_violation,
        )

    def respond_to_intervention(self, intervention_id: str, *, user_response: str, bypassed: bool = False) -> BehaviorIntervention:
        intervention = self.db.get(BehaviorIntervention, intervention_id)
        if intervention is None:
            raise InterventionNotFoundError("behavior intervention not found")
        if intervention.intervention_level == "BLOCK" and bypassed:
            raise BehaviorEvaluationError("BLOCK interventions cannot be bypassed")
        intervention.user_response = user_response
        intervention.bypassed = bypassed
        self._write_audit_log(
            action="behavior_intervention.responded",
            entity_type="BehaviorIntervention",
            entity_id=intervention.id,
            payload_json={
                "order_intent_id": intervention.order_intent_id,
                "intervention_level": intervention.intervention_level,
                "bypassed": bypassed,
            },
        )
        self.db.commit()
        self.db.refresh(intervention)
        return intervention

    def list_patterns(self, *, limit: int = 100) -> list[BehaviorPattern]:
        return list(
            self.db.scalars(select(BehaviorPattern).order_by(BehaviorPattern.created_at, BehaviorPattern.id).limit(limit)).all()
        )

    def list_interventions(self, *, limit: int = 100) -> list[BehaviorIntervention]:
        return list(
            self.db.scalars(
                select(BehaviorIntervention).order_by(BehaviorIntervention.created_at, BehaviorIntervention.id).limit(limit)
            ).all()
        )

    def build_profile(self, user_id: str) -> dict[str, Any]:
        patterns = list(
            self.db.scalars(
                select(BehaviorPattern)
                .where(BehaviorPattern.user_id == user_id)
                .order_by(BehaviorPattern.created_at.desc(), BehaviorPattern.id.desc())
            ).all()
        )
        interventions = list(
            self.db.scalars(
                select(BehaviorIntervention)
                .where(BehaviorIntervention.user_id == user_id)
                .order_by(BehaviorIntervention.created_at.desc(), BehaviorIntervention.id.desc())
            ).all()
        )
        recurring_patterns = sorted(
            (
                {
                    "pattern_type": pattern_type,
                    "count": count,
                    "latest_severity": latest_severity,
                }
                for pattern_type, count, latest_severity in self.db.execute(
                    select(
                        BehaviorPattern.pattern_type,
                        func.count(BehaviorPattern.id),
                        func.max(BehaviorPattern.severity),
                    )
                    .where(BehaviorPattern.user_id == user_id)
                    .group_by(BehaviorPattern.pattern_type)
                ).all()
            ),
            key=lambda item: (-int(item["count"]), str(item["pattern_type"])),
        )
        block_count = sum(1 for intervention in interventions if intervention.intervention_level == "BLOCK")
        bypass_count = sum(1 for intervention in interventions if intervention.bypassed)
        latest_intervention = interventions[0] if interventions else None
        baseline = "stable"
        if block_count > 0:
            baseline = "high_risk"
        elif bypass_count >= 2 or len(recurring_patterns) >= 3:
            baseline = "watch"
        summary = (
            f"Detected {len(patterns)} behavior events across {len(recurring_patterns)} pattern types; "
            f"{block_count} blocks and {bypass_count} bypassed interventions."
        )
        repeat_offenders = [pattern for pattern in recurring_patterns if int(pattern["count"]) >= 2]
        recent_30d_patterns = self._count_recent_patterns(user_id, days=30)
        recent_30d_bypasses = self._count_recent_bypasses(user_id, days=30)
        cumulative_penalty_score = block_count * 3 + bypass_count * 2 + len(repeat_offenders)
        return {
            "user_id": user_id,
            "total_patterns": len(patterns),
            "total_interventions": len(interventions),
            "bypassed_interventions": bypass_count,
            "block_interventions": block_count,
            "current_baseline": {
                "status": baseline,
                "latest_intervention_level": latest_intervention.intervention_level if latest_intervention else None,
                "latest_intervention_at": latest_intervention.created_at if latest_intervention else None,
                "recent_30d_patterns": recent_30d_patterns,
                "recent_30d_bypasses": recent_30d_bypasses,
                "cumulative_penalty_score": cumulative_penalty_score,
                "cooldown_recommended": recent_30d_bypasses >= 2 or block_count > 0,
            },
            "summary": summary,
            "top_patterns": recurring_patterns[:3],
            "recurring_patterns": recurring_patterns[:5],
            "repeat_offenders": repeat_offenders[:5],
        }

    def _detect_patterns(
        self,
        order_intent: OrderIntent,
        asset: Asset,
        thesis: InvestmentThesis | None,
        constitution: InvestmentConstitution | None,
        context: dict[str, Any],
    ) -> list[DetectedBehavior]:
        detections: list[DetectedBehavior] = []
        side = order_intent.side.lower()
        market_move = context.get("market_move") or {}
        recent_losses = context.get("recent_losses") or {}
        trade_history = context.get("trade_history") or []
        position_history = context.get("position_history") or {}
        explicit_flags = set(context.get("behavior_flags") or [])
        projected_position_pct = float(context.get("projected_position_pct") or context.get("order_position_pct") or 0)

        if "FOMO_BUYING" in explicit_flags or (
            side == "buy"
            and float(market_move.get("pct_change_1d") or market_move.get("pct_change") or 0) >= float(context.get("fomo_move_threshold_pct", 0.08))
        ):
            detections.append(self._detection("FOMO_BUYING", {"market_move": market_move, "side": side}))

        if "PANIC_SELLING" in explicit_flags or (
            side == "sell"
            and float(market_move.get("pct_change_1d") or market_move.get("pct_change") or 0) <= -float(context.get("panic_move_threshold_pct", 0.06))
            and not bool(context.get("thesis_invalidation_triggered", False))
        ):
            detections.append(self._detection("PANIC_SELLING", {"market_move": market_move, "side": side, "thesis_invalidated": False}))

        if "OVERTRADING" in explicit_flags or len(trade_history) >= int(context.get("overtrading_trade_count_threshold", 5)):
            detections.append(self._detection("OVERTRADING", {"trade_count": len(trade_history)}))

        if "REVENGE_TRADING" in explicit_flags or int(recent_losses.get("consecutive_loss_count") or 0) >= 2:
            detections.append(self._detection("REVENGE_TRADING", {"recent_losses": recent_losses}))

        unrealized_pnl_pct = float(position_history.get("unrealized_pnl_pct") or 0)
        if "AVERAGING_DOWN_AFTER_LOSSES" in explicit_flags or (
            side == "buy" and unrealized_pnl_pct <= -float(context.get("averaging_down_loss_threshold_pct", 0.08))
        ):
            detections.append(self._detection("AVERAGING_DOWN_AFTER_LOSSES", {"position_history": position_history, "side": side}))

        if "SELLING_WINNERS_TOO_EARLY" in explicit_flags or (
            side == "sell"
            and unrealized_pnl_pct >= float(context.get("winner_pct_threshold", 0.08))
            and int(position_history.get("holding_period_days") or 0) < int(context.get("min_holding_period_days", 30))
        ):
            detections.append(self._detection("SELLING_WINNERS_TOO_EARLY", {"position_history": position_history, "side": side}))

        if "HOLDING_LOSERS_TOO_LONG" in explicit_flags or (
            side != "sell"
            and thesis is not None
            and unrealized_pnl_pct <= -float(thesis.max_loss_tolerance_pct)
        ):
            detections.append(self._detection("HOLDING_LOSERS_TOO_LONG", {"position_history": position_history, "side": side}))

        max_single_position_pct = float(
            context.get("max_single_position_pct")
            or (constitution.max_single_position_pct if constitution is not None else 1)
        )
        if "CONCENTRATION_DRIFT" in explicit_flags or projected_position_pct > max_single_position_pct:
            detections.append(
                self._detection(
                    "CONCENTRATION_DRIFT",
                    {"projected_position_pct": projected_position_pct, "max_single_position_pct": max_single_position_pct},
                )
            )

        if "THESIS_CONFLICT_TRADE" in explicit_flags or bool(context.get("thesis_conflict", False)):
            detections.append(
                self._detection(
                    "THESIS_CONFLICT_TRADE",
                    {
                        "thesis_id": thesis.id if thesis else None,
                        "prior_user_statement": context.get("prior_user_statement") or (thesis.entry_reason if thesis else None),
                        "current_action": context.get("current_action") or f"{side} {asset.symbol}",
                    },
                )
            )

        trigger_source = str(context.get("trigger_source") or order_intent.source_type or "").lower()
        rationale = f"{order_intent.rationale or ''} {order_intent.user_rationale or ''}".lower()
        if "SOCIAL_MEDIA_TRIGGERED_TRADE" in explicit_flags or trigger_source in {"social_media", "twitter", "x"} or "social media" in rationale:
            detections.append(self._detection("SOCIAL_MEDIA_TRIGGERED_TRADE", {"trigger_source": trigger_source}))

        return detections

    def _escalate_detections(self, user_id: str, detections: list[DetectedBehavior]) -> list[DetectedBehavior]:
        escalated: list[DetectedBehavior] = []
        for detection in detections:
            prior_count = self._count_recent_patterns(user_id, days=30, pattern_type=detection.pattern_type)
            prior_bypasses = self._count_recent_bypasses(user_id, days=30, pattern_type=detection.pattern_type)
            new_level = detection.level
            if prior_count >= 2 and detection.level == "SOFT_WARNING":
                new_level = "HARD_CONFIRM"
            if prior_count >= 3 and detection.level == "HARD_CONFIRM":
                new_level = "BLOCK"
            if prior_bypasses >= 1 and detection.level == "HARD_CONFIRM":
                new_level = "BLOCK"
            escalated.append(
                DetectedBehavior(
                    pattern_type=detection.pattern_type,
                    level=new_level,
                    evidence={
                        **detection.evidence,
                        "recent_pattern_count_30d": prior_count,
                        "recent_bypasses_30d": prior_bypasses,
                    },
                    description=detection.description,
                    severity="critical" if new_level == "BLOCK" else "high" if new_level == "HARD_CONFIRM" else detection.severity,
                )
            )
        return escalated

    def _detection(self, pattern_type: str, evidence: dict[str, Any]) -> DetectedBehavior:
        level = PATTERN_DEFAULT_LEVEL[pattern_type]
        severity = "critical" if level == "BLOCK" else "high" if level == "HARD_CONFIRM" else "medium"
        return DetectedBehavior(
            pattern_type=pattern_type,
            level=level,
            evidence=evidence,
            description=f"Detected {pattern_type} while evaluating an order intent.",
            severity=severity,
        )

    def _store_pattern(self, user_id: str, asset_id: str, detection: DetectedBehavior) -> BehaviorPattern:
        pattern = BehaviorPattern(
            user_id=user_id,
            pattern_type=detection.pattern_type,
            asset_id=asset_id if detection.pattern_type != "NO_BEHAVIOR_PATTERN_DETECTED" else None,
            description=detection.description,
            evidence_json=detection.evidence,
            estimated_cost=0,
            frequency=1,
            severity=detection.severity,
        )
        self.db.add(pattern)
        self.db.flush()
        self._write_audit_log(
            action="behavior_pattern.detected",
            entity_type="BehaviorPattern",
            entity_id=pattern.id,
            payload_json={"user_id": user_id, "asset_id": asset_id, "pattern_type": detection.pattern_type},
        )
        return pattern

    def _store_intervention(
        self,
        *,
        user_id: str,
        pattern_id: str | None,
        order_intent_id: str,
        level: str,
        message: str,
    ) -> BehaviorIntervention:
        intervention = BehaviorIntervention(
            user_id=user_id,
            pattern_id=pattern_id,
            order_intent_id=order_intent_id,
            intervention_level=level,
            message=message,
            user_response=None,
            bypassed=False,
        )
        self.db.add(intervention)
        self.db.flush()
        self._write_audit_log(
            action="behavior_intervention.created",
            entity_type="BehaviorIntervention",
            entity_id=intervention.id,
            payload_json={"order_intent_id": order_intent_id, "pattern_id": pattern_id, "intervention_level": level},
        )
        return intervention

    def _create_thesis_violation(
        self,
        order_intent: OrderIntent,
        thesis: InvestmentThesis | None,
        user_id: str,
        primary: DetectedBehavior,
        context: dict[str, Any],
    ) -> ThesisViolation | None:
        if primary.pattern_type != "THESIS_CONFLICT_TRADE" or thesis is None:
            return None
        violation = ThesisViolation(
            thesis_id=thesis.id,
            user_id=user_id,
            related_order_intent_id=order_intent.id,
            violation_type="THESIS_CONFLICT_TRADE",
            prior_user_statement=context.get("prior_user_statement") or thesis.entry_reason,
            current_action=context.get("current_action") or f"{order_intent.side} {order_intent.asset_id}",
            explanation=context.get("thesis_conflict_explanation") or "Order action conflicts with the recorded investment thesis.",
            intervention_level=primary.level,
            resolved_status="open",
        )
        self.db.add(violation)
        self.db.flush()
        self._write_audit_log(
            action="thesis_violation.created_by_behavior_engine",
            entity_type="ThesisViolation",
            entity_id=violation.id,
            payload_json={"order_intent_id": order_intent.id, "thesis_id": thesis.id},
        )
        return violation

    def _message(
        self,
        order_intent: OrderIntent,
        asset: Asset,
        thesis: InvestmentThesis | None,
        primary: DetectedBehavior,
        context: dict[str, Any],
    ) -> str:
        thesis_sentence = ""
        if thesis is not None:
            thesis_sentence = f'Your recorded thesis for {asset.symbol} says: "{thesis.entry_reason}". '
        side = order_intent.side.lower()
        if primary.pattern_type == "FOMO_BUYING":
            return (
                f"{thesis_sentence}{asset.symbol} has moved quickly and this buy looks momentum-triggered. "
                "Before continuing, confirm whether the thesis changed or whether you are chasing the move."
            )
        if primary.pattern_type == "PANIC_SELLING":
            return (
                f"{thesis_sentence}Today's drawdown does not by itself prove the thesis is invalid. "
                "Are you selling because the thesis changed, or because the drawdown feels uncomfortable?"
            )
        if primary.pattern_type == "CONCENTRATION_DRIFT":
            evidence = primary.evidence
            return (
                f"This order would push projected position weight to {evidence.get('projected_position_pct')}, "
                f"above the allowed max {evidence.get('max_single_position_pct')}. The behavior engine blocks this concentration drift."
            )
        if primary.pattern_type == "THESIS_CONFLICT_TRADE":
            return (
                f"{thesis_sentence}This {side} action conflicts with your recorded thesis. "
                "Confirm what new fact changed before this order can proceed."
            )
        if primary.pattern_type == "SOCIAL_MEDIA_TRIGGERED_TRADE":
            return (
                f"{thesis_sentence}This trade appears to be triggered by social media rather than your playbook or thesis. "
                "Confirm the structured evidence before continuing."
            )
        if primary.pattern_type == "NO_BEHAVIOR_PATTERN_DETECTED":
            return "No configured harmful behavior pattern was detected. The order still requires decision gates, risk checks, and approval."
        return (
            f"{thesis_sentence}Detected {primary.pattern_type}. "
            "Review the evidence and confirm this action is consistent with your constitution, playbook, and thesis."
        )

    def _required_user_action(self, level: str) -> str:
        if level == "BLOCK":
            return "Revise or cancel the order; this intervention cannot be bypassed."
        if level == "HARD_CONFIRM":
            return "Write a specific confirmation explaining the changed facts before proceeding."
        if level == "SOFT_WARNING":
            return "Acknowledge the warning before proceeding."
        return "No user action required."

    def _combined_evidence(self, detections: list[DetectedBehavior]) -> dict[str, Any]:
        return {detection.pattern_type: detection.evidence for detection in detections}

    def _resolve_user_id(self, order_intent: OrderIntent, thesis: InvestmentThesis | None, context: dict[str, Any]) -> str:
        if context.get("user_id"):
            return str(context["user_id"])
        if thesis is not None:
            return thesis.user_id
        return "default-user"

    def _active_constitution(self, user_id: str) -> InvestmentConstitution | None:
        return self.db.scalar(
            select(InvestmentConstitution)
            .where(InvestmentConstitution.user_id == user_id, InvestmentConstitution.is_active.is_(True))
            .order_by(InvestmentConstitution.updated_at.desc(), InvestmentConstitution.id.desc())
            .limit(1)
        )

    def _count_recent_patterns(self, user_id: str, *, days: int, pattern_type: str | None = None) -> int:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = select(func.count(BehaviorPattern.id)).where(
            BehaviorPattern.user_id == user_id,
            BehaviorPattern.created_at >= since,
        )
        if pattern_type is not None:
            query = query.where(BehaviorPattern.pattern_type == pattern_type)
        return int(self.db.scalar(query) or 0)

    def _count_recent_bypasses(self, user_id: str, *, days: int, pattern_type: str | None = None) -> int:
        since = datetime.now(timezone.utc) - timedelta(days=days)
        query = (
            select(func.count(BehaviorIntervention.id))
            .select_from(BehaviorIntervention)
            .where(
                BehaviorIntervention.user_id == user_id,
                BehaviorIntervention.created_at >= since,
                BehaviorIntervention.bypassed.is_(True),
            )
        )
        if pattern_type is not None:
            query = query.join(BehaviorPattern, BehaviorPattern.id == BehaviorIntervention.pattern_id).where(
                BehaviorPattern.pattern_type == pattern_type
            )
        return int(self.db.scalar(query) or 0)

    def _write_audit_log(self, *, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="behavior-engine",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )
