from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account
from app.models import Approval
from app.models import Asset
from app.models import AuditLog
from app.models import OrderDraft
from app.models import OrderIntent
from app.models import Position
from app.models import RiskCheck
from app.models.core import utc_now
from app.services.decision_gates import DecisionGateBlockedError
from app.services.decision_gates import DecisionGateService


ORDER_DRAFT_ACCOUNT_MODES = {"paper", "manual"}


class RiskCheckNotFoundError(ValueError):
    pass


class RiskCheckBlockedError(ValueError):
    pass


class ApprovalBlockedError(ValueError):
    pass


class RiskEngineService:
    def __init__(self, db: Session):
        self.db = db

    def check_order(self, order_intent: OrderIntent, context: dict[str, Any]) -> RiskCheck:
        asset = self.db.get(Asset, order_intent.asset_id)
        account = self.db.get(Account, order_intent.account_id)
        if asset is None or account is None:
            raise RiskCheckBlockedError("order intent asset or account is unavailable")

        rules = self._evaluate_rules(order_intent, asset, account, context)
        failed_rules = [rule["rule"] for rule in rules if not rule["passed"]]
        passed = not failed_rules
        risk_check = RiskCheck(
            order_intent_id=order_intent.id,
            status="passed" if passed else "blocked",
            hard_rule_passed=passed,
            rules_json={
                "rules": rules,
                "context": context,
                "order_notional": float(order_notional(order_intent)),
            },
            reason="all hard rules passed" if passed else ", ".join(failed_rules),
        )
        self.db.add(risk_check)
        self.db.flush()
        self._write_audit_log(
            action="risk_check.passed" if passed else "risk_check.blocked",
            entity_type="RiskCheck",
            entity_id=risk_check.id,
            payload_json={
                "order_intent_id": order_intent.id,
                "status": risk_check.status,
                "failed_rules": failed_rules,
            },
        )
        self.db.commit()
        self.db.refresh(risk_check)
        return risk_check

    def create_draft_after_risk(self, order_intent: OrderIntent, context: dict[str, Any]) -> OrderDraft:
        risk_check = self.check_order(order_intent, context)
        if not risk_check.hard_rule_passed:
            raise RiskCheckBlockedError(risk_check.reason or "risk check blocked order draft")
        try:
            decision_gate_results = DecisionGateService(self.db).require_all_gates_passed(order_intent.id)
        except DecisionGateBlockedError as exc:
            raise RiskCheckBlockedError(str(exc)) from exc

        draft = OrderDraft(
            order_intent_id=order_intent.id,
            risk_status="passed",
            behavior_status="passed",
            decision_gate_results=decision_gate_results,
            approval_policy={"required": True, "source": "decision_gates"},
            approval_status="pending",
            execution_status="not_executable",
        )
        self.db.add(draft)
        self.db.flush()
        self._write_audit_log(
            action="order_draft.created_after_risk",
            entity_type="OrderDraft",
            entity_id=draft.id,
            payload_json={"order_intent_id": order_intent.id, "risk_check_id": risk_check.id},
        )
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def require_latest_risk_passed(self, order_intent_id: str) -> RiskCheck:
        risk_check = self.latest_risk_check(order_intent_id)
        if risk_check is None:
            raise RiskCheckNotFoundError("order draft requires a completed risk check")
        if not risk_check.hard_rule_passed:
            raise RiskCheckBlockedError(risk_check.reason or "latest risk check blocked order draft")
        return risk_check

    def latest_risk_check(self, order_intent_id: str) -> RiskCheck | None:
        return self.db.scalar(
            select(RiskCheck)
            .where(RiskCheck.order_intent_id == order_intent_id)
            .order_by(RiskCheck.created_at.desc(), RiskCheck.id.desc())
            .limit(1)
        )

    def approve_draft(self, draft: OrderDraft, approver_id: str | None, decision_reason: str | None) -> Approval:
        self._ensure_draft_approvable(draft)
        approval = Approval(
            order_draft_id=draft.id,
            status="approved",
            approver_id=approver_id,
            decision_reason=decision_reason,
            decided_at=utc_now(),
        )
        draft.approval_status = "approved"
        self.db.add(approval)
        self.db.flush()
        self._write_audit_log(
            action="order_draft.approved",
            entity_type="Approval",
            entity_id=approval.id,
            payload_json={"order_draft_id": draft.id, "approver_id": approver_id},
        )
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def reject_draft(self, draft: OrderDraft, approver_id: str | None, decision_reason: str | None) -> Approval:
        approval = Approval(
            order_draft_id=draft.id,
            status="rejected",
            approver_id=approver_id,
            decision_reason=decision_reason,
            decided_at=utc_now(),
        )
        draft.approval_status = "rejected"
        self.db.add(approval)
        self.db.flush()
        self._write_audit_log(
            action="order_draft.rejected",
            entity_type="Approval",
            entity_id=approval.id,
            payload_json={"order_draft_id": draft.id, "approver_id": approver_id, "reason": decision_reason},
        )
        self.db.commit()
        self.db.refresh(approval)
        return approval

    def modify_draft(self, draft: OrderDraft, decision_reason: str | None) -> OrderDraft:
        draft.approval_status = "modified"
        self.db.flush()
        self._write_audit_log(
            action="order_draft.modified",
            entity_type="OrderDraft",
            entity_id=draft.id,
            payload_json={"order_draft_id": draft.id, "reason": decision_reason},
        )
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def _ensure_draft_approvable(self, draft: OrderDraft) -> None:
        if draft.risk_status != "passed":
            raise ApprovalBlockedError("order draft cannot be approved without passed risk status")
        risk_check = self.require_latest_risk_passed(draft.order_intent_id)
        if not risk_check.hard_rule_passed:
            raise ApprovalBlockedError("latest risk check is not passed")

    def _evaluate_rules(
        self,
        order_intent: OrderIntent,
        asset: Asset,
        account: Account,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        notional = order_notional(order_intent)
        order_mode = context.get("order_mode", "manual")
        total_equity = decimal_context(context, "total_equity", self._portfolio_total_value(account.id))
        current_position_value = decimal_context(context, "current_position_value", self._position_value(account.id, asset.id))
        final_position_value = final_value_after_order(order_intent, current_position_value, notional)
        final_position_pct = safe_divide(final_position_value, total_equity)

        rules = [
            rule("live_trading_enabled", account.mode != "live" or bool(account.live_trading_enabled), {"account_mode": account.mode}),
            rule("account_mode_allows_order_draft", account.mode in ORDER_DRAFT_ACCOUNT_MODES, {"account_mode": account.mode}),
            rule("asset_tradable", bool(asset.tradable), {"tradable": asset.tradable}),
            rule(
                "asset_manual_or_auto_enabled",
                bool(asset.auto_enabled if order_mode == "auto" else asset.manual_enabled),
                {"order_mode": order_mode, "manual_enabled": asset.manual_enabled, "auto_enabled": asset.auto_enabled},
            ),
            rule("max_order_notional", notional <= decimal_context(context, "max_order_notional", Decimal("10000")), {"order_notional": float(notional)}),
            rule(
                "max_position_pct",
                final_position_pct <= decimal_context(context, "max_position_pct", Decimal("0.25")),
                {"final_position_pct": float(final_position_pct), "total_equity": float(total_equity)},
            ),
            rule(
                "max_daily_loss",
                decimal_context(context, "account_daily_loss", Decimal("0")) <= decimal_context(context, "max_daily_loss", Decimal("1000")),
                {"account_daily_loss": context.get("account_daily_loss", 0)},
            ),
            rule(
                "max_leverage",
                decimal_context(context, "current_leverage", Decimal("0")) <= decimal_context(context, "max_leverage", Decimal("1")),
                {"current_leverage": context.get("current_leverage", 0)},
            ),
            rule("liquidity_check", bool(context.get("liquidity_passed", True)), {"liquidity_passed": context.get("liquidity_passed", True)}),
            rule(
                "volatility_threshold",
                decimal_context(context, "volatility", Decimal("0")) <= decimal_context(context, "max_volatility", Decimal("1")),
                {"volatility": context.get("volatility", 0)},
            ),
            rule("kill_switch", not bool(context.get("kill_switch", False)), {"kill_switch": context.get("kill_switch", False)}),
        ]
        return rules

    def _portfolio_total_value(self, account_id: str) -> Decimal:
        values = [to_decimal(position.market_value) for position in self.db.scalars(select(Position).where(Position.account_id == account_id)).all()]
        return sum(values, Decimal("0")) or Decimal("100000")

    def _position_value(self, account_id: str, asset_id: str) -> Decimal:
        values = [
            to_decimal(position.market_value)
            for position in self.db.scalars(select(Position).where(Position.account_id == account_id, Position.asset_id == asset_id)).all()
        ]
        return sum(values, Decimal("0"))

    def _write_audit_log(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        payload_json: dict[str, Any],
    ) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="phase8-risk-engine",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )


def rule(name: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"rule": name, "passed": passed, "details": details}


def order_notional(order_intent: OrderIntent) -> Decimal:
    if order_intent.notional is not None:
        return to_decimal(order_intent.notional)
    if order_intent.quantity is not None and order_intent.limit_price is not None:
        return to_decimal(order_intent.quantity) * to_decimal(order_intent.limit_price)
    return Decimal("0")


def final_value_after_order(order_intent: OrderIntent, current_value: Decimal, notional: Decimal) -> Decimal:
    if order_intent.side == "sell":
        return max(Decimal("0"), current_value - notional)
    return current_value + notional


def decimal_context(context: dict[str, Any], key: str, default: Decimal) -> Decimal:
    return to_decimal(context.get(key, default))


def to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator == 0:
        return Decimal("0")
    return numerator / denominator
