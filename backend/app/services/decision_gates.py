from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from decimal import Decimal
import hashlib
import json
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import AutomationPolicy
from app.models import BehaviorIntervention
from app.models import BehaviorPattern
from app.models import DataCatalogEntry
from app.services.manual_trade_evidence import ManualEvidenceError, validate_manual_evidence
from app.models import DataSnapshot
from app.models import DataQualityReport
from app.models import DecisionGate
from app.models import InvestmentConstitution
from app.models import InvestmentThesis
from app.models import OrderIntent
from app.models import Quote
from app.models import ResearchReport
from app.models import RiskBudget
from app.models import StrategyPlaybook
from app.models import StrategyRule
from app.models import ThesisViolation
from app.models import ThesisCheckpoint
from app.services.behavior import BehaviorEngine
from app.services.account_risk_context import server_account_context


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

        context = server_account_context(self.db, order_intent, context)
        user_id = self._resolve_user_id(order_intent, context)
        outcomes = [
            self._research_gate(order_intent, context),
            self._thesis_gate(order_intent, asset, user_id, context),
            self._risk_gate(order_intent, asset, account, user_id, context),
            self._behavior_gate(order_intent, asset, user_id, context),
            self._execution_gate(order_intent, asset, context),
        ]

        for outcome in outcomes:
            outcome.evidence["evaluation_context"] = {
                key: value for key, value in context.items() if not key.startswith("_")
            }
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
        self.require_current_research(order_intent_id, latest["RESEARCH_GATE"].id)
        results = {
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
        self.require_current_nonresearch(order_intent_id, results)
        return results

    def require_current_research(self, order_intent_id: str, gate_id: str | None, *, commit: bool = True) -> None:
        """Recheck the exact research evidence used by this draft, never a newer gate."""
        gate = self.db.get(DecisionGate, gate_id) if gate_id else None
        intent = self.db.get(OrderIntent, order_intent_id)
        evidence = (gate.evidence_json or {}) if gate else {}
        reason = None
        if (
            gate is None or gate.order_intent_id != order_intent_id
            or gate.gate_type != "RESEARCH_GATE" or gate.status != PASSING_GATE_STATUS
            or intent is None or not evidence.get("research_fingerprint")
            or evidence.get("research_fingerprint_version") != 1
        ):
            reason = "research evidence grant missing; preview and create a new draft"
        else:
            current = self._research_gate(
                intent, dict(evidence.get("validation_context") or {}),
                pinned_report_id=evidence.get("research_report_id"),
            )
            if current.status != PASSING_GATE_STATUS:
                reason = "current research evidence blocked: " + ", ".join(current.blocking_reasons or current.warnings)
            elif current.evidence["research_fingerprint"] != evidence["research_fingerprint"]:
                reason = "research evidence changed; preview and create a new draft"
        self._write_audit_log(
            action="research_evidence.blocked" if reason else "research_evidence.revalidated",
            entity_type="OrderIntent", entity_id=order_intent_id,
            payload_json={"gate_id": gate_id, "reason": reason},
        )
        if commit:
            self.db.commit()
        if reason:
            raise DecisionGateBlockedError(reason)

    def require_current_nonresearch(self, order_intent_id: str, results: dict, *, draft_id: str | None = None, commit: bool = True) -> None:
        """Re-evaluate bound gates from persisted inputs and current server state."""
        intent = self.db.get(OrderIntent, order_intent_id)
        asset = self.db.get(Asset, intent.asset_id) if intent else None
        account = self.db.get(Account, intent.account_id) if intent else None
        reasons = []
        if intent is None or asset is None or account is None:
            reasons.append("order context unavailable")
        else:
            for gate_type in REQUIRED_GATE_TYPES[1:]:
                gate_id = (results.get(gate_type) or {}).get("gate_id")
                gate = self.db.get(DecisionGate, gate_id) if gate_id else None
                if (gate is None or gate.order_intent_id != order_intent_id or gate.gate_type != gate_type
                        or gate.status != PASSING_GATE_STATUS or "evaluation_context" not in (gate.evidence_json or {})):
                    reasons.append(f"{gate_type}: saved evaluation unavailable; preview a new draft")
                    continue
                context = server_account_context(
                    self.db, intent, dict(gate.evidence_json["evaluation_context"]), draft_id=draft_id,
                )
                user_id = self._resolve_user_id(intent, context)
                if gate_type == "THESIS_GATE":
                    current = self._thesis_gate(intent, asset, user_id, context, record_violations=False)
                elif gate_type == "RISK_GATE":
                    current = self._risk_gate(intent, asset, account, user_id, context)
                elif gate_type == "BEHAVIOR_GATE":
                    current = self._behavior_gate(intent, asset, user_id, context, record_detections=False)
                else:
                    current = self._execution_gate(intent, asset, context)
                if current.status != PASSING_GATE_STATUS:
                    details = current.blocking_reasons or current.warnings
                    reasons.append(f"{gate_type}: " + ", ".join(details))
        self._write_audit_log(
            action="decision_gate.revalidation_blocked" if reasons else "decision_gate.revalidated",
            entity_type="OrderIntent", entity_id=order_intent_id,
            payload_json={"draft_id": draft_id, "reasons": reasons},
        )
        if commit:
            self.db.commit()
        if reasons:
            raise DecisionGateBlockedError("current decision gates blocked: " + "; ".join(reasons))

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

    def _research_gate(self, order_intent: OrderIntent, context: dict[str, Any], *, pinned_report_id: str | None = None) -> GateOutcome:
        blocking: list[str] = []
        warnings: list[str] = []
        data_snapshot_id = context.get("data_snapshot_id")
        if not data_snapshot_id:
            blocking.append("data_snapshot_missing")
        if context.get("data_quality_status", "acceptable") not in {"ok", "acceptable", "passed"}:
            blocking.append("data_quality_unacceptable")
        quality_report = self._latest_quality_report(str(data_snapshot_id)) if data_snapshot_id else None
        min_data_quality_score = max(0.75, float(context.get("min_data_quality_score", 0.75)))
        if quality_report is None:
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
        catalog_entry = None
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

        # Only successfully imported quote rows establish market coverage. Requested
        # symbols may include failed imports and cannot authorize another asset.
        snapshot = self.db.get(DataSnapshot, str(data_snapshot_id)) if data_snapshot_id else None
        if data_snapshot_id and snapshot is None:
            blocking.append("data_snapshot_unavailable")
        asset = self.db.get(Asset, order_intent.asset_id)
        quotes = (snapshot.data_json or {}).get("quotes") if snapshot else None
        if snapshot is not None and snapshot.snapshot_type == "market_candles":
            quotes = (snapshot.data_json or {}).get("symbols")
        if isinstance(quotes, list):
            def covers_order(row: Any) -> bool:
                if not isinstance(row, dict) or asset is None:
                    return False
                if row.get("asset_id") and str(row["asset_id"]) != asset.id:
                    return False
                if str(row.get("symbol", "")).upper() != asset.symbol.upper():
                    return False
                return all(
                    not row.get(key) or str(row[key]).upper() == str(getattr(asset, key) or "").upper()
                    for key in ("venue", "currency")
                )

            if not any(covers_order(row) for row in quotes):
                blocking.append("data_snapshot_asset_mismatch")

        manual_evidence = None
        if snapshot is not None and snapshot.snapshot_type == "manual_paper_quote":
            try:
                manual_evidence = validate_manual_evidence(self.db, order_intent, snapshot)
            except ManualEvidenceError as exc:
                blocking.append(f"manual_evidence_invalid:{exc}")
        report_required = manual_evidence is None

        report = None
        trace = order_intent.evidence_json or {}
        selected_report_id = trace.get("report_id") or trace.get("research_report_id")
        if trace.get("report_id") and trace.get("research_report_id") and trace["report_id"] != trace["research_report_id"]:
            blocking.append("research_report_reference_conflict")
        if pinned_report_id or selected_report_id:
            report = self.db.get(ResearchReport, str(pinned_report_id or selected_report_id))
            if report is None:
                blocking.append("selected_research_report_missing")
        elif data_snapshot_id:
            report = self.db.scalar(
                select(ResearchReport)
                .where(
                    ResearchReport.data_snapshot_id == data_snapshot_id,
                    or_(ResearchReport.asset_id == order_intent.asset_id, ResearchReport.asset_id.is_(None)),
                )
                .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
                .limit(1)
            )
        if report is not None:
            if report.data_snapshot_id != data_snapshot_id:
                blocking.append("research_report_snapshot_mismatch")
            if report.asset_id is not None and report.asset_id != order_intent.asset_id:
                blocking.append("research_report_asset_mismatch")
        if report_required and report is None:
            blocking.append("research_report_missing")
        if report is not None:
            if not report.bullish_case:
                blocking.append("bullish_case_missing")
            if not report.bearish_case:
                blocking.append("bearish_case_missing")
            if not report.key_risks:
                blocking.append("key_risks_missing")
            if float(report.confidence or 0) < max(0.5, float(context.get("min_research_confidence", 0.5))):
                blocking.append("research_confidence_below_threshold")

        validation_context = {
            "data_snapshot_id": data_snapshot_id,
            "data_quality_status": context.get("data_quality_status", "acceptable"),
            "quality_report_required": True,
            "min_data_quality_score": min_data_quality_score,
            "research_report_required": report_required,
            "min_research_confidence": context.get("min_research_confidence", 0.5),
            "hallucination_flags": hallucination_flags,
        }
        fingerprint = self._stable_hash(evidence_value({
            "version": 1, "asset_id": order_intent.asset_id,
            "asset_identity": {key: getattr(asset, key) for key in ("symbol", "venue", "currency", "asset_type", "chain_id", "contract_address")} if asset else None,
            "order_trace": order_intent.evidence_json or {},
            "context": validation_context,
            "records": [
                {column.key: getattr(record, column.key) for column in record.__table__.columns}
                if record is not None else None
                for record in (snapshot, quality_report, catalog_entry, report) + ((manual_evidence,) if manual_evidence is not None else ())
            ],
        }))

        return self._outcome(
            "RESEARCH_GATE",
            blocking,
            warnings,
            evidence={
                "research_fingerprint_version": 1,
                "research_fingerprint": fingerprint,
                "validation_context": validation_context,
                "data_snapshot_id": data_snapshot_id,
                "quality_report_id": quality_report.id if quality_report else None,
                "manual_evidence": manual_evidence is not None,
                "selected_research_report_id": selected_report_id,
                "asset_id": order_intent.asset_id,
                "research_report_id": report.id if report else None,
                "research_report_confidence": float(report.confidence or 0) if report else None,
                "citation_refs": (order_intent.evidence_json or {}).get("citation_refs", []),
            },
        )

    def _thesis_gate(self, order_intent: OrderIntent, asset: Asset, user_id: str, context: dict[str, Any], *, record_violations: bool = True) -> GateOutcome:
        blocking: list[str] = []
        warnings: list[str] = []
        thesis = self.db.get(InvestmentThesis, order_intent.investment_thesis_id) if order_intent.investment_thesis_id else None
        has_user_rationale = bool((order_intent.user_rationale or order_intent.rationale or "").strip())
        if thesis is None and not has_user_rationale:
            blocking.append("investment_thesis_or_user_rationale_missing")
        if order_intent.investment_thesis_id and thesis is None:
            blocking.append("investment_thesis_unavailable")
        if thesis is not None and thesis.asset_id != order_intent.asset_id:
            blocking.append("investment_thesis_asset_mismatch")
        if thesis is not None and thesis.account_id and thesis.account_id != order_intent.account_id:
            blocking.append("investment_thesis_account_mismatch")
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
        if record_violations and thesis is not None and (conflict or invalidated):
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
        blocking.extend(context.get("_account_risk_errors", []))
        if context.get("kill_switch"):
            blocking.append("kill_switch_engaged")
        constitution = self._active_constitution(user_id)
        final_position_pct = float(context.get("current_position_pct", 0)) + float(context.get("order_position_pct", 0))

        if constitution is None:
            blocking.append("active_investment_constitution_missing")
        else:
            max_single_position_pct = constitution_limit(context, "max_single_position_pct", constitution.max_single_position_pct)
            max_asset_class_pct = constitution_limit(context, "max_asset_class_pct", constitution.max_asset_class_pct)
            max_crypto_pct = constitution_limit(context, "max_crypto_pct", constitution.max_crypto_pct)
            max_single_exchange_pct = constitution_limit(context, "max_single_exchange_pct", constitution.max_single_exchange_pct)
            max_daily_loss_pct = constitution_limit(context, "max_daily_loss_pct", constitution.max_daily_loss_pct)
            max_monthly_drawdown_pct = constitution_limit(context, "max_monthly_drawdown_pct", constitution.max_monthly_drawdown_pct)

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
        elif max(order_notional(order_intent), to_decimal(context.get("_server_order_notional", 0))) > to_decimal(budget.max_order_notional):
            blocking.append("risk_budget_max_order_notional_exceeded")

        rule_blocking, rule_warnings, rule_evidence = self._strategy_rule_checks(order_intent, asset, context)
        blocking.extend(rule_blocking)
        warnings.extend(rule_warnings)

        return self._outcome("RISK_GATE", blocking, warnings, {"strategy_rules": rule_evidence, "account_risk": context.get("_account_risk_evidence")})

    def _strategy_rule_checks(
        self,
        order_intent: OrderIntent,
        asset: Asset,
        context: dict[str, Any],
    ) -> tuple[list[str], list[str], list[dict[str, Any]]]:
        """Enforce active rules on the explicit or thesis-linked playbook."""
        thesis = self.db.get(InvestmentThesis, order_intent.investment_thesis_id) if order_intent.investment_thesis_id else None
        thesis_playbook_id = thesis.strategy_playbook_id if thesis else None
        playbook_id = order_intent.strategy_playbook_id or thesis_playbook_id
        if order_intent.strategy_playbook_id and thesis_playbook_id and order_intent.strategy_playbook_id != thesis_playbook_id:
            return ["strategy_playbook_reference_conflict"], [], []
        if not playbook_id:
            return [], [], []
        playbook = self.db.get(StrategyPlaybook, playbook_id)
        if playbook is None or not playbook.is_active:
            return ["strategy_playbook_unavailable_or_inactive"], [], []
        rules = list(
            self.db.scalars(
                select(StrategyRule)
                .where(StrategyRule.strategy_playbook_id == playbook_id, StrategyRule.is_active.is_(True))
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
                violated = max(order_notional(order_intent), to_decimal(context.get("_server_order_notional", 0))) > to_decimal(conditions.get("max_notional", 0))
            elif rule.rule_type == "forbidden_symbols":
                symbols = [str(item).upper() for item in conditions.get("symbols", [])]
                violated = asset.symbol.upper() in symbols
            elif rule.rule_type == "allowed_sides":
                sides = [str(item).lower() for item in conditions.get("sides", [])]
                violated = bool(sides) and str(order_intent.side).lower() not in sides
            elif rule.rule_type == "min_thesis_confidence":
                confidence = float(thesis.confidence) if thesis is not None else None
                violated = confidence is None or confidence < float(conditions.get("min_confidence", 0))
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

    def _behavior_gate(self, order_intent: OrderIntent, asset: Asset, user_id: str, context: dict[str, Any], *, record_detections: bool = True) -> GateOutcome:
        interventions = list(self.db.scalars(select(BehaviorIntervention).where(
            BehaviorIntervention.order_intent_id == order_intent.id,
        )).all())
        unresolved = [item for item in interventions if (
            item.intervention_level not in {"SILENT_RECORD", "SOFT_WARNING", "HARD_CONFIRM"}
            or (item.intervention_level == "HARD_CONFIRM" and not (item.bypassed and (item.user_response or "").strip()))
            or (item.intervention_level == "SOFT_WARNING" and not (item.user_response or "").strip())
        )]
        if unresolved:
            return self._outcome("BEHAVIOR_GATE", [
                f"behavior_intervention:{item.intervention_level}:{item.id}" for item in unresolved
            ], [], {"intervention_ids": [item.id for item in unresolved]})
        behavior_flags = [flag for flag in context.get("behavior_flags", []) if flag in HARD_BEHAVIOR_FLAGS]
        if behavior_flags:
            if not record_detections:
                return self._outcome("BEHAVIOR_GATE", ["behavior_flags_require_new_preview"], [])
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
        if latest_quote is None:
            blocking.append("latest_quote_missing")
        if latest_quote is not None and self._quote_age_seconds(latest_quote) > min(900, max(0, int(context.get("max_quote_age_seconds", 900)))):
            blocking.append("latest_quote_stale")
        if latest_quote is not None:
            as_of = latest_quote.as_of if latest_quote.as_of.tzinfo else latest_quote.as_of.replace(tzinfo=timezone.utc)
            if as_of > datetime.now(timezone.utc):
                blocking.append("latest_quote_in_future")
            if not to_decimal(latest_quote.price).is_finite() or to_decimal(latest_quote.price) <= 0:
                blocking.append("latest_quote_price_invalid")
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
        if order_intent.automation_policy_id and policy is None:
            blocking.append("automation_policy_unavailable")
        if policy is not None:
            if not policy.is_active:
                blocking.append("automation_policy_inactive")
            if policy.account_id and policy.account_id != order_intent.account_id:
                blocking.append("automation_policy_account_mismatch")
            if policy.asset_id and policy.asset_id != order_intent.asset_id:
                blocking.append("automation_policy_asset_mismatch")
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

    def _stable_hash(self, payload: Any) -> str:
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


def constitution_limit(context: dict[str, Any], name: str, saved_limit: Any) -> float:
    """A request may tighten a stored policy, but may never relax it."""
    saved = float(saved_limit)
    requested = context.get(name)
    return saved if requested is None else min(saved, float(requested))


def evidence_value(value: Any) -> Any:
    """Typed canonical data, stable across UTC and Numeric DB round trips."""
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return ["datetime", aware.astimezone(timezone.utc).isoformat()]
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["boolean", value]
    if isinstance(value, (int, float, Decimal)):
        return ["number", str(Decimal(str(value)).normalize())]
    if isinstance(value, dict):
        return ["object", [[key, evidence_value(value[key])] for key in sorted(value)]]
    if isinstance(value, list):
        return ["array", [evidence_value(item) for item in value]]
    return ["string", value]
