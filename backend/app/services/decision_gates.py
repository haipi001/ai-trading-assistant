from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from decimal import Decimal
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import AutomationPolicy
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DecisionGate
from app.models import InvestmentConstitution
from app.models import InvestmentThesis
from app.models import OrderIntent
from app.models import Quote
from app.models import ResearchReport
from app.models import RiskBudget
from app.models import StrategyRule
from app.models import ThesisViolation
from app.models import ThesisCheckpoint
from app.services.behavior import BehaviorEngine


REQUIRED_GATE_TYPES = ["RESEARCH_GATE", "THESIS_GATE", "RISK_GATE", "BEHAVIOR_GATE", "EXECUTION_GATE"]
PASSING_GATE_STATUS = "PASSED"
HARD_BEHAVIOR_FLAGS = {
    "FOMO_BUYING",
    "PANIC_SELLING",
    "OVERTRADING",
    "REVENGE_TRADING",
    "AVERAGING_DOWN_AFTER_LOSSES",
    "SELLING_WINNERS_TOO_EARLY",
    "HOLDING_LOSERS_TOO_LONG",
    "CONCENTRATION_DRIFT",
    "THESIS_CONFLICT_TRADE",
    "SOCIAL_MEDIA_TRIGGERED_TRADE",
}


class DecisionGateBlockedError(ValueError):
    pass


@dataclass
class GateOutcome:
    gate_type: str
    status: str
    score: float
    blocking_reasons: list[str]
    warnings: list[str]
    recommended_intervention_level: str
    evidence: dict[str, Any]


class DecisionGateService:
    def __init__(self, db: Session):
        self.db = db

    def evaluate_order(self, order_intent_id: str, context: dict[str, Any]) -> list[DecisionGate]:
        order_intent = self.db.get(OrderIntent, order_intent_id)
        if order_intent is None:
            raise DecisionGateBlockedError("order intent not found")
        asset = self.db.get(Asset, order_intent.asset_id)
        account = self.db.get(Account, order_intent.account_id)
        if asset is None or account is None:
            raise DecisionGateBlockedError("order intent asset or account is unavailable")

        user_id = self._resolve_user_id(order_intent, context)
        outcomes = [
            self._research_gate(order_intent, context),
            self._thesis_gate(order_intent, asset, user_id, context),
            self._risk_gate(order_intent, asset, account, user_id, context),
            self._behavior_gate(order_intent, asset, user_id, context),
            self._execution_gate(order_intent, asset, context),
        ]

        gates = [self._store_gate(order_intent.id, outcome) for outcome in outcomes]
        self.db.commit()
        for gate in gates:
            self.db.refresh(gate)
        return gates

    def require_all_gates_passed(self, order_intent_id: str) -> dict[str, Any]:
        latest = self.latest_gate_results(order_intent_id)
        missing = [gate_type for gate_type in REQUIRED_GATE_TYPES if gate_type not in latest]
        failed = {
            gate_type: gate.status
            for gate_type, gate in latest.items()
            if gate_type in REQUIRED_GATE_TYPES and gate.status != PASSING_GATE_STATUS
        }
        if missing or failed:
            raise DecisionGateBlockedError(f"order draft requires all decision gates passed; missing={missing}; failed={failed}")
        return {
            gate_type: {
                "gate_id": gate.id,
                "status": gate.status,
                "score": float(gate.score or 0),
                "blocking_reasons": gate.blocking_reasons_json,
                "warnings": gate.warnings_json,
                "recommended_intervention_level": gate.recommended_intervention_level,
            }
            for gate_type, gate in latest.items()
            if gate_type in REQUIRED_GATE_TYPES
        }

    def latest_gate_results(self, order_intent_id: str) -> dict[str, DecisionGate]:
        gates = self.db.scalars(
            select(DecisionGate)
            .where(DecisionGate.order_intent_id == order_intent_id)
            .order_by(DecisionGate.created_at.desc(), DecisionGate.id.desc())
        ).all()
        latest: dict[str, DecisionGate] = {}
        for gate in gates:
            if gate.gate_type not in latest:
                latest[gate.gate_type] = gate
        return latest

    def gate_timeline(self, order_intent_id: str) -> list[DecisionGate]:
        return list(
            self.db.scalars(
                select(DecisionGate)
                .where(DecisionGate.order_intent_id == order_intent_id)
                .order_by(DecisionGate.created_at, DecisionGate.id)
            ).all()
        )

    def replay_order(self, order_intent_id: str) -> dict[str, Any]:
        order_intent = self.db.get(OrderIntent, order_intent_id)
        if order_intent is None:
            raise DecisionGateBlockedError("order intent not found")

        latest = self.latest_gate_results(order_intent_id)
        timeline = self.gate_timeline(order_intent_id)
        missing = [gate_type for gate_type in REQUIRED_GATE_TYPES if gate_type not in latest]
        failed = [
            gate_type
            for gate_type, gate in latest.items()
            if gate_type in REQUIRED_GATE_TYPES and gate.status != PASSING_GATE_STATUS
        ]

        replayed_at = datetime.now(timezone.utc)
        items = [
            self._replay_item(gate_type, latest.get(gate_type))
            for gate_type in REQUIRED_GATE_TYPES
        ]
        replay_status = "blocked" if missing else ("review_required" if failed else "completed")
        evidence_packet = {
            "order_intent_id": order_intent.id,
            "policy_version": "decision-gate-local-v1",
            "replayed_at": replayed_at.isoformat(),
            "latest_gate_ids": {gate_type: latest[gate_type].id for gate_type in latest if gate_type in REQUIRED_GATE_TYPES},
            "missing_gate_types": missing,
            "failed_gate_types": failed,
            "timeline_gate_count": len(timeline),
            "items": items,
            "order_trace": dict(order_intent.evidence_json or {}),
        }
        replay_hash = self._stable_hash(evidence_packet)
        result = {
            **evidence_packet,
            "replay_status": replay_status,
            "replay_hash": replay_hash,
            "checks": [
                {
                    "key": "gate_history",
                    "status": "blocked" if missing else "passed",
                    "detail": "All required gates have a stored result." if not missing else f"Missing gates: {', '.join(missing)}",
                },
                {
                    "key": "policy_version",
                    "status": "passed",
                    "detail": "Replay uses immutable stored gate evidence with decision-gate-local-v1.",
                },
                {
                    "key": "evidence_chain",
                    "status": "passed" if timeline else "blocked",
                    "detail": "Stored gate evidence was hashed for audit replay." if timeline else "No gate evidence exists yet.",
                },
                {
                    "key": "execution_boundary",
                    "status": "passed",
                    "detail": "Replay is review-only and cannot create orders, approve drafts, or execute trades.",
                },
            ],
            "order_creation_allowed": False,
            "execution_available": False,
            "live_execution_available": False,
            "next_actions": self._replay_next_actions(missing, failed),
        }
        self._write_audit_log(
            action="decision_gate.replayed",
            entity_type="OrderIntent",
            entity_id=order_intent.id,
            payload_json={
                "order_intent_id": order_intent.id,
                "replay_status": replay_status,
                "replay_hash": replay_hash,
                "missing_gate_types": missing,
                "failed_gate_types": failed,
                "order_creation_allowed": False,
                "execution_available": False,
            },
        )
        self.db.commit()
        return result

    def _research_gate(self, order_intent: OrderIntent, context: dict[str, Any]) -> GateOutcome:
        blocking: list[str] = []
        warnings: list[str] = []
        data_snapshot_id = context.get("data_snapshot_id")
        if not data_snapshot_id:
            blocking.append("data_snapshot_missing")
        if context.get("data_quality_status", "acceptable") not in {"ok", "acceptable", "passed"}:
            blocking.append("data_quality_unacceptable")
        quality_report = self._latest_quality_report(str(data_snapshot_id)) if data_snapshot_id else None
        min_data_quality_score = float(context.get("min_data_quality_score", 0.75))
        if context.get("quality_report_required", True) and quality_report is None:
            blocking.append("data_quality_report_missing")
        if quality_report is not None:
            quality_score = float(quality_report.score or 0)
            quality_status = self._quality_status(quality_report)
            if quality_score < min_data_quality_score:
                blocking.append("data_quality_score_below_threshold")
            elif quality_score < max(min_data_quality_score, 0.85):
                warnings.append("data_quality_score_warning")
            if quality_status in {"blocked", "failed", "stale"}:
                blocking.append("data_quality_report_status_blocked")
        hallucination_flags = context.get("hallucination_flags") or []
        if hallucination_flags:
            blocking.append("hallucination_flags_present")

        # Data catalog trust: when the cited snapshot is cataloged, the
        # catalog's own verdict is enforced here — an entry that is blocked or
        # not usable for trading decisions cannot pass the research gate.
        if data_snapshot_id:
            catalog_entry = self.db.scalar(
                select(DataCatalogEntry)
                .where(DataCatalogEntry.data_snapshot_id == str(data_snapshot_id))
                .order_by(DataCatalogEntry.created_at.desc(), DataCatalogEntry.id.desc())
                .limit(1)
            )
            if catalog_entry is not None:
                if str(catalog_entry.quality_status).upper() in {"BLOCKED", "FAILED"}:
                    blocking.append("data_catalog_quality_blocked")
                elif not catalog_entry.usable_for_trading:
                    blocking.append("data_catalog_not_usable_for_trading")

        report = None
        if data_snapshot_id:
            report = self.db.scalar(
                select(ResearchReport)
                .where(ResearchReport.data_snapshot_id == data_snapshot_id)
                .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
                .limit(1)
            )
        if context.get("research_report_required", True) and report is None:
            blocking.append("research_report_missing")
        if report is not None:
            if not report.bullish_case:
                blocking.append("bullish_case_missing")
            if not report.bearish_case:
                blocking.append("bearish_case_missing")
            if not report.key_risks:
                blocking.append("key_risks_missing")
            if float(report.confidence or 0) < float(context.get("min_research_confidence", 0.5)):
                blocking.append("research_confidence_below_threshold")

        return self._outcome(
            "RESEARCH_GATE",
            blocking,
            warnings,
            evidence={
                "data_snapshot_id": data_snapshot_id,
                "quality_report_id": quality_report.id if quality_report else None,
                "research_report_id": report.id if report else None,
                "research_report_confidence": float(report.confidence or 0) if report else None,
                "citation_refs": (order_intent.evidence_json or {}).get("citation_refs", []),
            },
        )

    def _thesis_gate(self, order_intent: OrderIntent, asset: Asset, user_id: str, context: dict[str, Any]) -> GateOutcome:
        blocking: list[str] = []
        warnings: list[str] = []
        thesis = self.db.get(InvestmentThesis, order_intent.investment_thesis_id) if order_intent.investment_thesis_id else None
        has_user_rationale = bool((order_intent.user_rationale or order_intent.rationale or "").strip())
        if thesis is None and not has_user_rationale:
            blocking.append("investment_thesis_or_user_rationale_missing")
        if thesis is not None and thesis.status != "active":
            blocking.append("investment_thesis_not_active")

        latest_checkpoint = None
        if thesis is not None:
            latest_checkpoint = self.db.scalar(
                select(ThesisCheckpoint)
                .where(ThesisCheckpoint.thesis_id == thesis.id)
                .order_by(ThesisCheckpoint.created_at.desc(), ThesisCheckpoint.id.desc())
                .limit(1)
            )
            if latest_checkpoint is not None and latest_checkpoint.invalidates_thesis:
                invalidated = True
            if latest_checkpoint is not None and latest_checkpoint.weakens_thesis:
                warnings.append("latest_thesis_checkpoint_weakens_thesis")

        conflict = bool(context.get("thesis_conflict", False))
        invalidated = bool(context.get("thesis_invalidation_triggered", False)) or bool(
            latest_checkpoint and latest_checkpoint.invalidates_thesis
        )
        if conflict:
            blocking.append("order_conflicts_with_active_thesis")
        if invalidated:
            blocking.append("thesis_invalidation_condition_triggered")
        if thesis is not None and (conflict or invalidated):
            self._create_thesis_violation(order_intent, thesis, user_id, context)

        return self._outcome(
            "THESIS_GATE",
            blocking,
            warnings,
            evidence={
                "thesis_id": thesis.id if thesis else None,
                "thesis_status": thesis.status if thesis else None,
                "thesis_checkpoint_id": latest_checkpoint.id if latest_checkpoint else None,
                "checkpoint_type": latest_checkpoint.checkpoint_type if latest_checkpoint else None,
                "checkpoint_supports": latest_checkpoint.supports_thesis if latest_checkpoint else None,
                "checkpoint_weakens": latest_checkpoint.weakens_thesis if latest_checkpoint else None,
                "checkpoint_invalidates": latest_checkpoint.invalidates_thesis if latest_checkpoint else None,
            },
        )

    def _risk_gate(self, order_intent: OrderIntent, asset: Asset, account: Account, user_id: str, context: dict[str, Any]) -> GateOutcome:
        blocking: list[str] = []
        warnings: list[str] = []
        constitution = self._active_constitution(user_id)
        final_position_pct = float(context.get("current_position_pct", 0)) + float(context.get("order_position_pct", 0))

        if constitution is None:
            blocking.append("active_investment_constitution_missing")
        else:
            max_single_position_pct = float(context.get("max_single_position_pct") or constitution.max_single_position_pct)
            max_asset_class_pct = float(context.get("max_asset_class_pct") or constitution.max_asset_class_pct)
            max_crypto_pct = float(context.get("max_crypto_pct") or constitution.max_crypto_pct)
            max_single_exchange_pct = float(context.get("max_single_exchange_pct") or constitution.max_single_exchange_pct)
            max_daily_loss_pct = float(context.get("max_daily_loss_pct") or constitution.max_daily_loss_pct)
            max_monthly_drawdown_pct = float(context.get("max_monthly_drawdown_pct") or constitution.max_monthly_drawdown_pct)

            if final_position_pct > max_single_position_pct:
                blocking.append("max_single_position_pct_exceeded")
            if float(context.get("asset_class_pct", 0)) > max_asset_class_pct:
                blocking.append("max_asset_class_pct_exceeded")
            if (asset.asset_type == "crypto" or float(context.get("crypto_pct", 0)) > 0) and float(context.get("crypto_pct", 0)) > max_crypto_pct:
                blocking.append("max_crypto_pct_exceeded")
            if float(context.get("exchange_pct", 0)) > max_single_exchange_pct:
                blocking.append("max_single_exchange_pct_exceeded")
            if float(context.get("daily_loss_pct", 0)) > max_daily_loss_pct:
                blocking.append("max_daily_loss_pct_exceeded")
            if float(context.get("monthly_drawdown_pct", 0)) > max_monthly_drawdown_pct:
                blocking.append("max_monthly_drawdown_pct_exceeded")
            if float(context.get("current_leverage", 0)) > 0 and not constitution.leverage_allowed:
                blocking.append("leverage_not_allowed")
            if asset.symbol in constitution.forbidden_assets or asset.id in constitution.forbidden_assets:
                blocking.append("asset_forbidden_by_constitution")
            if order_intent.side in constitution.forbidden_actions or context.get("action") in constitution.forbidden_actions:
                blocking.append("action_forbidden_by_constitution")

        budget = self._risk_budget(user_id, account.id, asset.asset_type)
        if budget is None:
            warnings.append("risk_budget_missing")
        elif order_notional(order_intent) > to_decimal(budget.max_order_notional):
            blocking.append("risk_budget_max_order_notional_exceeded")

        rule_blocking, rule_warnings, rule_evidence = self._strategy_rule_checks(order_intent, asset, context)
        blocking.extend(rule_blocking)
        warnings.extend(rule_warnings)

        return self._outcome("RISK_GATE", blocking, warnings, {"strategy_rules": rule_evidence} if rule_evidence else None)

    def _strategy_rule_checks(
        self,
        order_intent: OrderIntent,
        asset: Asset,
        context: dict[str, Any],
    ) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        """StrategyPlaybook rules sit above the order workflow: active rules on
        the order's thesis playbook are enforced here, so a rule the user wrote
        after a review actually gates the next trade instead of being metadata."""
        if not order_intent.investment_thesis_id:
            return [], [], []
        thesis = self.db.get(InvestmentThesis, order_intent.investment_thesis_id)
        if thesis is None or not thesis.strategy_playbook_id:
            return [], [], []
        rules = list(
            self.db.scalars(
                select(StrategyRule)
                .where(StrategyRule.strategy_playbook_id == thesis.strategy_playbook_id, StrategyRule.is_active.is_(True))
                .order_by(StrategyRule.priority.asc(), StrategyRule.created_at.asc())
            ).all()
        )
        blocking: list[str] = []
        warnings: list[str] = []
        evidence: list[dict[str, Any]] = []
        final_position_pct = float(context.get("current_position_pct", 0)) + float(context.get("order_position_pct", 0))
        for rule in rules:
            conditions = rule.conditions_json or {}
            violated = False
            unsupported = False
            if rule.rule_type == "max_position_weight":
                violated = final_position_pct > float(conditions.get("max_position_pct", 100))
            elif rule.rule_type == "max_order_notional":
                violated = order_notional(order_intent) > to_decimal(conditions.get("max_notional", 0))
            elif rule.rule_type == "forbidden_symbols":
                symbols = [str(item).upper() for item in conditions.get("symbols", [])]
                violated = asset.symbol.upper() in symbols
            elif rule.rule_type == "allowed_sides":
                sides = [str(item).lower() for item in conditions.get("sides", [])]
                violated = bool(sides) and str(order_intent.side).lower() not in sides
            elif rule.rule_type == "min_thesis_confidence":
                confidence = context.get("thesis_confidence")
                violated = confidence is not None and float(confidence) < float(conditions.get("min_confidence", 0))
            else:
                unsupported = True
            reason = f"strategy_rule:{rule.rule_type}:{rule.id}"
            if unsupported:
                warnings.append(f"strategy_rule_type_unsupported:{rule.rule_type}")
            elif violated:
                action = str((rule.actions_json or {}).get("action") or "block").lower()
                if action == "warn":
                    warnings.append(reason)
                else:
                    blocking.append(reason)
            evidence.append(
                {
                    "rule_id": rule.id,
                    "rule_type": rule.rule_type,
                    "priority": rule.priority,
                    "violated": violated,
                    "unsupported": unsupported,
                }
            )
        return blocking, warnings, evidence

    def _behavior_gate(self, order_intent: OrderIntent, asset: Asset, user_id: str, context: dict[str, Any]) -> GateOutcome:
        behavior_flags = [flag for flag in context.get("behavior_flags", []) if flag in HARD_BEHAVIOR_FLAGS]
        if behavior_flags:
            result = BehaviorEngine(self.db).evaluate_order(
                order_intent.id,
                {
                    **context,
                    "user_id": user_id,
                    "behavior_flags": behavior_flags,
                    "order_position_pct": context.get("order_position_pct", 0),
                    "projected_position_pct": float(context.get("current_position_pct", 0)) + float(context.get("order_position_pct", 0)),
                },
            )
            if result.level == "BLOCK":
                return GateOutcome(
                    gate_type="BEHAVIOR_GATE",
                    status="BLOCKED",
                    score=0,
                    blocking_reasons=[f"behavior_block:{pattern.pattern_type}" for pattern in result.patterns],
                    warnings=[],
                    recommended_intervention_level="BLOCK",
                    evidence={"behavior_flags": behavior_flags},
                )
            if result.level == "SOFT_WARNING":
                return GateOutcome(
                    gate_type="BEHAVIOR_GATE",
                    status="WARNING",
                    score=0.75,
                    blocking_reasons=[],
                    warnings=[f"behavior_risk:{pattern.pattern_type}" for pattern in result.patterns],
                    recommended_intervention_level="SOFT_WARNING",
                    evidence={"behavior_flags": behavior_flags},
                )
            return GateOutcome(
                gate_type="BEHAVIOR_GATE",
                status="HARD_CONFIRM_REQUIRED",
                score=0.45,
                blocking_reasons=[],
                warnings=[f"behavior_risk:{pattern.pattern_type}" for pattern in result.patterns],
                recommended_intervention_level=result.level,
                evidence={"behavior_flags": behavior_flags},
            )
        return self._outcome("BEHAVIOR_GATE", [], [])

    def _execution_gate(self, order_intent: OrderIntent, asset: Asset, context: dict[str, Any]) -> GateOutcome:
        blocking: list[str] = []
        warnings: list[str] = []
        latest_quote = self.db.scalar(
            select(Quote).where(Quote.asset_id == asset.id).order_by(Quote.as_of.desc(), Quote.id.desc()).limit(1)
        )
        if context.get("latest_quote_required", True) and latest_quote is None:
            blocking.append("latest_quote_missing")
        if latest_quote is not None and self._quote_age_seconds(latest_quote) > int(context.get("max_quote_age_seconds", 900)):
            blocking.append("latest_quote_stale")
        if not bool(context.get("source_timestamp_valid", True)):
            blocking.append("source_timestamp_invalid")
        if context.get("broker_status", "healthy") != "healthy":
            blocking.append("broker_status_unhealthy")
        if context.get("exchange_status", "healthy") != "healthy":
            blocking.append("exchange_status_unhealthy")
        if float(context.get("expected_slippage_pct", 0)) > float(context.get("max_slippage_pct", 0.01)):
            blocking.append("expected_slippage_too_high")
        if not bool(context.get("order_size_executable", True)):
            blocking.append("order_size_not_executable")

        policy = self.db.get(AutomationPolicy, order_intent.automation_policy_id) if order_intent.automation_policy_id else None
        if policy is not None:
            action = context.get("action", "CREATE_ORDER_DRAFT")
            if action in policy.forbidden_actions:
                blocking.append("automation_policy_forbids_action")
            if policy.allowed_actions and action not in policy.allowed_actions:
                blocking.append("automation_policy_action_not_allowed")
            if context.get("execution_mode") == "live" and policy.automation_level not in {"A4_APPROVAL_EXECUTION", "A5_CONTROLLED_AUTO"}:
                blocking.append("automation_policy_does_not_allow_live_execution_mode")

        return self._outcome("EXECUTION_GATE", blocking, warnings)

    def _store_gate(self, order_intent_id: str, outcome: GateOutcome) -> DecisionGate:
        order_intent = self.db.get(OrderIntent, order_intent_id)
        gate = DecisionGate(
            order_intent_id=order_intent_id,
            gate_type=outcome.gate_type,
            status=outcome.status,
            score=outcome.score,
            blocking_reasons_json=outcome.blocking_reasons,
            warnings_json=outcome.warnings,
            evidence_json={
                **outcome.evidence,
                "order_trace": dict(order_intent.evidence_json or {}) if order_intent else {},
            },
            recommended_intervention_level=outcome.recommended_intervention_level,
            evaluator="decision_gate_service",
        )
        self.db.add(gate)
        self.db.flush()
        self._write_audit_log(
            action="decision_gate.evaluated",
            entity_type="DecisionGate",
            entity_id=gate.id,
            payload_json={
                "order_intent_id": order_intent_id,
                "gate_type": gate.gate_type,
                "status": gate.status,
                "blocking_reasons": gate.blocking_reasons_json,
                "warnings": gate.warnings_json,
                "evidence": gate.evidence_json,
                "recommended_intervention_level": gate.recommended_intervention_level,
            },
        )
        return gate

    def _replay_item(self, gate_type: str, gate: DecisionGate | None) -> dict[str, Any]:
        if gate is None:
            return {
                "gate_type": gate_type,
                "gate_label": self._gate_label(gate_type),
                "replayed_status": "missing",
                "original_gate_id": None,
                "original_status": None,
                "original_score": None,
                "blocking_reasons": [],
                "warnings": [],
                "evidence_hash": None,
                "evidence_summary": "No stored gate result exists yet.",
            }
        evidence = dict(gate.evidence_json or {})
        return {
            "gate_type": gate_type,
            "gate_label": self._gate_label(gate_type),
            "replayed_status": "matched",
            "original_gate_id": gate.id,
            "original_status": gate.status,
            "original_score": float(gate.score or 0),
            "blocking_reasons": list(gate.blocking_reasons_json or []),
            "warnings": list(gate.warnings_json or []),
            "evidence_hash": self._stable_hash(
                {
                    "gate_id": gate.id,
                    "gate_type": gate.gate_type,
                    "status": gate.status,
                    "score": float(gate.score or 0),
                    "blocking_reasons": gate.blocking_reasons_json,
                    "warnings": gate.warnings_json,
                    "evidence": evidence,
                    "created_at": gate.created_at.isoformat(),
                }
            ),
            "evidence_summary": self._evidence_summary(evidence),
        }

    def _replay_next_actions(self, missing: list[str], failed: list[str]) -> list[str]:
        if missing:
            return [
                "Run the decision gate check before replay can prove this plan.",
                "Keep the plan in manual review; replay cannot create an order.",
            ]
        if failed:
            return [
                "Review the blocked or warning gates before any draft approval.",
                "Use the evidence hashes for audit comparison after fixing the plan.",
            ]
        return [
            "Use this replay packet for audit or regression review.",
            "Continue to risk review and human approval if you still want a draft.",
        ]

    def _gate_label(self, gate_type: str) -> str:
        labels = {
            "RESEARCH_GATE": "研究闸门",
            "THESIS_GATE": "逻辑闸门",
            "RISK_GATE": "风险闸门",
            "BEHAVIOR_GATE": "行为闸门",
            "EXECUTION_GATE": "执行闸门",
        }
        return labels.get(gate_type, gate_type)

    def _evidence_summary(self, evidence: dict[str, Any]) -> str:
        visible_keys = [key for key, value in evidence.items() if value not in (None, "", [], {})]
        if not visible_keys:
            return "Stored gate evidence is empty."
        return f"Stored evidence keys: {', '.join(visible_keys[:6])}."

    def _stable_hash(self, payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _outcome(
        self,
        gate_type: str,
        blocking: list[str],
        warnings: list[str],
        evidence: dict[str, Any] | None = None,
    ) -> GateOutcome:
        if blocking:
            return GateOutcome(gate_type, "BLOCKED", 0, blocking, warnings, "BLOCK", evidence or {})
        if warnings:
            return GateOutcome(gate_type, "WARNING", 0.75, [], warnings, "SOFT_WARNING", evidence or {})
        return GateOutcome(gate_type, "PASSED", 1, [], [], "SILENT_RECORD", evidence or {})

    def _resolve_user_id(self, order_intent: OrderIntent, context: dict[str, Any]) -> str:
        if context.get("user_id"):
            return str(context["user_id"])
        if order_intent.investment_thesis_id:
            thesis = self.db.get(InvestmentThesis, order_intent.investment_thesis_id)
            if thesis is not None:
                return thesis.user_id
        if order_intent.automation_policy_id:
            policy = self.db.get(AutomationPolicy, order_intent.automation_policy_id)
            if policy is not None:
                return policy.user_id
        return "default-user"

    def _active_constitution(self, user_id: str) -> InvestmentConstitution | None:
        return self.db.scalar(
            select(InvestmentConstitution)
            .where(InvestmentConstitution.user_id == user_id, InvestmentConstitution.is_active.is_(True))
            .order_by(InvestmentConstitution.updated_at.desc(), InvestmentConstitution.id.desc())
            .limit(1)
        )

    def _risk_budget(self, user_id: str, account_id: str, asset_class: str) -> RiskBudget | None:
        return self.db.scalar(
            select(RiskBudget)
            .where(
                RiskBudget.user_id == user_id,
                RiskBudget.asset_class == asset_class,
                (RiskBudget.account_id == account_id) | (RiskBudget.account_id.is_(None)),
            )
            .order_by(RiskBudget.account_id.desc(), RiskBudget.updated_at.desc(), RiskBudget.id.desc())
            .limit(1)
        )

    def _latest_quality_report(self, data_snapshot_id: str) -> DataQualityReport | None:
        return self.db.scalar(
            select(DataQualityReport)
            .where(DataQualityReport.data_snapshot_id == data_snapshot_id)
            .order_by(DataQualityReport.created_at.desc(), DataQualityReport.id.desc())
            .limit(1)
        )

    def _quality_status(self, report: DataQualityReport) -> str:
        details = report.details_json or {}
        explicit = details.get("status")
        if isinstance(explicit, str) and explicit:
            return explicit
        score = float(report.score or 0)
        if score < 0.5:
            return "blocked"
        if score < 0.75:
            return "warning"
        return "ok"

    def _create_thesis_violation(self, order_intent: OrderIntent, thesis: InvestmentThesis, user_id: str, context: dict[str, Any]) -> None:
        violation = ThesisViolation(
            thesis_id=thesis.id,
            user_id=user_id,
            related_order_intent_id=order_intent.id,
            violation_type="THESIS_CONFLICT",
            prior_user_statement=context.get("prior_user_statement") or thesis.entry_reason,
            current_action=context.get("current_action") or f"{order_intent.side} {order_intent.asset_id}",
            explanation=context.get("thesis_conflict_explanation") or "Order conflicts with active thesis or invalidation conditions.",
            intervention_level="HARD_CONFIRM",
            resolved_status="open",
        )
        self.db.add(violation)
        self.db.flush()
        self._write_audit_log(
            action="thesis_violation.created_by_gate",
            entity_type="ThesisViolation",
            entity_id=violation.id,
            payload_json={"order_intent_id": order_intent.id, "thesis_id": thesis.id},
        )

    def _create_behavior_pattern(self, user_id: str, asset_id: str, behavior_flags: list[str]) -> BehaviorPattern:
        pattern_type = behavior_flags[0]
        pattern = BehaviorPattern(
            user_id=user_id,
            pattern_type=pattern_type,
            asset_id=asset_id,
            description=f"Detected behavior risk while evaluating order: {', '.join(behavior_flags)}.",
            evidence_json={"flags": behavior_flags},
            estimated_cost=0,
            frequency=1,
            severity="high",
        )
        self.db.add(pattern)
        self.db.flush()
        self._write_audit_log(
            action="behavior_pattern.detected_by_gate",
            entity_type="BehaviorPattern",
            entity_id=pattern.id,
            payload_json={"user_id": user_id, "asset_id": asset_id, "flags": behavior_flags},
        )
        return pattern

    def _create_behavior_intervention(self, user_id: str, pattern_id: str, order_intent_id: str, behavior_flags: list[str]) -> None:
        intervention = BehaviorIntervention(
            user_id=user_id,
            pattern_id=pattern_id,
            order_intent_id=order_intent_id,
            intervention_level="HARD_CONFIRM",
            message=f"Behavior risk detected: {', '.join(behavior_flags)}. Hard confirmation is required before continuing.",
            user_response=None,
            bypassed=False,
        )
        self.db.add(intervention)
        self.db.flush()
        self._write_audit_log(
            action="behavior_intervention.created_by_gate",
            entity_type="BehaviorIntervention",
            entity_id=intervention.id,
            payload_json={"order_intent_id": order_intent_id, "pattern_id": pattern_id, "flags": behavior_flags},
        )

    def _quote_age_seconds(self, quote: Quote) -> float:
        as_of = quote.as_of
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - as_of).total_seconds()

    def _write_audit_log(self, *, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="decision-gate-service",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


def order_notional(order_intent: OrderIntent) -> Decimal:
    if order_intent.notional is not None:
        return to_decimal(order_intent.notional)
    if order_intent.quantity is not None and order_intent.limit_price is not None:
        return to_decimal(order_intent.quantity) * to_decimal(order_intent.limit_price)
    return Decimal("0")


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))
