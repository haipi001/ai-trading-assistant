from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import StrategyPlaybook
from app.models import StrategyRule


class StrategyRuleError(ValueError):
    pass


class StrategyRuleNotFoundError(StrategyRuleError):
    pass


class StrategyRulesService:
    def __init__(self, db: Session):
        self.db = db

    def list_rules(self, strategy_playbook_id: str | None = None, limit: int = 100) -> list[StrategyRule]:
        query = select(StrategyRule)
        if strategy_playbook_id:
            query = query.where(StrategyRule.strategy_playbook_id == strategy_playbook_id)
        try:
            return list(
                self.db.scalars(
                    query.order_by(StrategyRule.priority.asc(), StrategyRule.created_at.desc(), StrategyRule.id.desc()).limit(limit)
                ).all()
            )
        except SQLAlchemyError:
            self.db.rollback()
            return []

    def create_rule(self, payload: dict[str, Any]) -> StrategyRule:
        self._require_playbook(payload["strategy_playbook_id"])
        rule = StrategyRule(**payload)
        self.db.add(rule)
        self.db.flush()
        self._write_audit_log(
            action="strategy_rule.created",
            entity_id=rule.id,
            payload_json=payload | {"order_creation_available": False},
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update_rule(self, rule_id: str, payload: dict[str, Any]) -> StrategyRule:
        rule = self.db.get(StrategyRule, rule_id)
        if rule is None:
            raise StrategyRuleNotFoundError("strategy rule not found")
        for key, value in payload.items():
            if value is not None:
                setattr(rule, key, value)
        self.db.flush()
        self._write_audit_log(
            action="strategy_rule.updated",
            entity_id=rule.id,
            payload_json=payload | {"order_creation_available": False},
        )
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def disable_rule(self, rule_id: str) -> None:
        rule = self.db.get(StrategyRule, rule_id)
        if rule is None:
            raise StrategyRuleNotFoundError("strategy rule not found")
        rule.is_active = False
        self.db.flush()
        self._write_audit_log(
            action="strategy_rule.disabled",
            entity_id=rule.id,
            payload_json={"strategy_playbook_id": rule.strategy_playbook_id, "order_creation_available": False},
        )
        self.db.commit()

    def _require_playbook(self, strategy_playbook_id: str) -> StrategyPlaybook:
        playbook = self.db.get(StrategyPlaybook, strategy_playbook_id)
        if playbook is None:
            raise StrategyRuleError("strategy playbook not found")
        return playbook

    def _write_audit_log(self, *, action: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="strategy-rules-service",
                action=action,
                entity_type="StrategyRule",
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )
