from dataclasses import asdict
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from app.models import Account
from app.models import Asset
from app.models import AuditLog
from app.models import StrategyPlaybook
from app.services.automation_policy import AutomationPolicyEngine
from app.services.automation_policy import AutomationPolicyNotImplementedError


ACTION_BY_KIND = {
    "dca": "DCA",
    "rebalance": "REBALANCE",
    "stop-loss": "STOP_LOSS",
    "take-profit": "TAKE_PROFIT",
}


class ControlledAutoError(ValueError):
    pass


class ControlledAutoNotFoundError(ControlledAutoError):
    pass


class ControlledAutoService:
    def __init__(self, db: Session):
        self.db = db

    def evaluate(self, kind: str, payload: dict[str, Any], user_id: str = "default-user") -> dict[str, Any]:
        action = self._action(kind)
        self._validate_entities(payload)
        order_notional, numeric_blockers = self._order_notional(payload)
        policy_details: dict[str, Any] = {}
        policy_blockers: list[str] = []

        try:
            evaluation = AutomationPolicyEngine(self.db).evaluate(
                user_id=user_id,
                account_id=payload["account_id"],
                asset_id=payload["asset_id"],
                strategy_playbook_id=payload.get("strategy_playbook_id"),
                action=action,
                order_notional=float(order_notional),
                gates_passed=False,
                risk_budget_passed=False,
                human_approved=False,
                live_trading_enabled=False,
            )
            policy_details = {
                "policy": asdict(evaluation.policy),
                "can_execute_controlled_auto": evaluation.can_execute_controlled_auto,
                "requires_human_approval": evaluation.requires_human_approval,
            }
            policy_blockers = list(evaluation.blocking_reasons)
        except AutomationPolicyNotImplementedError as exc:
            policy_blockers = ["automation_policy_not_implemented"]
            policy_details = {"automation_policy_error": str(exc)}

        blocking_reasons = self._dedupe(
            numeric_blockers
            + policy_blockers
            + [
                "controlled_auto_execution_not_implemented",
                "requires_human_review",
                "order_intent_creation_disabled_for_controlled_auto",
                "real_broker_call_forbidden",
            ]
        )
        details = {
            "requested_action": action,
            "execution_available": False,
            "order_intent_created": False,
            "order_notional": str(order_notional),
            "real_broker_call_performed": False,
            "mode": "evaluation_only",
        } | policy_details
        response = {
            "passed": False,
            "blocking_reasons": blocking_reasons,
            "warnings": ["controlled_auto_is_readiness_only"],
            "details": details,
        }
        self._write_audit_log(
            action="controlled_auto.evaluated",
            entity_id=payload["asset_id"],
            payload_json=response | {"payload": payload},
        )
        self.db.commit()
        return response

    def execute(self, kind: str, payload: dict[str, Any], user_id: str = "default-user") -> dict[str, Any]:
        evaluation = self.evaluate(kind, payload, user_id=user_id)
        response = {
            "order_intent_id": "not-created",
            "status": "blocked",
            "details": evaluation["details"]
            | {
                "blocking_reasons": evaluation["blocking_reasons"],
                "controlled_auto_execution_performed": False,
            },
        }
        self._write_audit_log(
            action="controlled_auto.execution_blocked",
            entity_id=payload["asset_id"],
            payload_json=response | {"payload": payload},
        )
        self.db.commit()
        return response

    def _validate_entities(self, payload: dict[str, Any]) -> None:
        if self.db.get(Asset, payload["asset_id"]) is None:
            raise ControlledAutoNotFoundError("asset not found")
        if self.db.get(Account, payload["account_id"]) is None:
            raise ControlledAutoNotFoundError("account not found")
        playbook_id = payload.get("strategy_playbook_id")
        if playbook_id and self.db.get(StrategyPlaybook, playbook_id) is None:
            raise ControlledAutoNotFoundError("strategy playbook not found")

    def _action(self, kind: str) -> str:
        action = ACTION_BY_KIND.get(kind)
        if action is None:
            raise ControlledAutoError("unsupported controlled auto action")
        return action

    def _order_notional(self, payload: dict[str, Any]) -> tuple[Decimal, list[str]]:
        blockers: list[str] = []
        quantity = self._decimal_field(payload, "target_quantity", blockers)
        price = (
            self._decimal_field(payload, "max_price", blockers)
            or self._decimal_field(payload, "current_price", blockers)
            or self._decimal_field(payload, "target_price", blockers)
        )
        if quantity is None or price is None:
            return Decimal("0"), blockers + ["controlled_auto_missing_quantity_or_price"]
        return quantity * price, blockers

    def _decimal_field(self, payload: dict[str, Any], field: str, blockers: list[str]) -> Decimal | None:
        raw_value = payload.get(field)
        if raw_value in (None, ""):
            return None
        try:
            value = Decimal(str(raw_value))
        except (InvalidOperation, ValueError):
            blockers.append(f"invalid_numeric_field:{field}")
            return None
        if value < 0:
            blockers.append(f"negative_numeric_field:{field}")
            return None
        return value

    def _write_audit_log(self, *, action: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="controlled-auto-service",
                action=action,
                entity_type="ControlledAuto",
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if value not in seen:
                result.append(value)
                seen.add(value)
        return result
