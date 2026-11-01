from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models import AutomationPolicy
from app.models import RiskBudget


LEVEL_RANK = {
    "A0_READ_ONLY": 0,
    "A1_RESEARCH": 1,
    "A2_ALERT": 2,
    "A3_ORDER_DRAFT": 3,
    "A4_APPROVAL_EXECUTION": 4,
    "A5_CONTROLLED_AUTO": 5,
}

CONTROLLED_AUTO_ACTIONS = {
    "DCA",
    "REBALANCE",
    "STOP_LOSS",
    "TAKE_PROFIT",
    "STABLECOIN_RISK_MIGRATION",
}


class AutomationPolicyError(ValueError):
    pass


class AutomationPolicyNotImplementedError(AutomationPolicyError):
    pass


@dataclass(frozen=True)
class EffectiveAutomationPolicy:
    id: str | None
    user_id: str
    account_id: str | None
    asset_id: str | None
    strategy_playbook_id: str | None
    automation_level: str
    max_notional_per_order: float
    max_orders_per_day: int
    requires_approval: bool
    allowed_actions: list[str]
    forbidden_actions: list[str]
    is_active: bool
    source: str


@dataclass(frozen=True)
class AutomationPolicyEvaluation:
    policy: EffectiveAutomationPolicy
    action: str
    can_create_order_intent: bool
    can_create_order_draft: bool
    requires_human_approval: bool
    can_execute_paper: bool
    can_execute_live: bool
    can_execute_controlled_auto: bool
    blocking_reasons: list[str]


class AutomationPolicyEngine:
    def __init__(self, db: Session):
        self.db = db

    def get_effective_policy(
        self,
        user_id: str,
        account_id: str | None = None,
        asset_id: str | None = None,
        strategy_playbook_id: str | None = None,
    ) -> EffectiveAutomationPolicy:
        policies = self.db.scalars(
            select(AutomationPolicy)
            .where(AutomationPolicy.user_id == user_id, AutomationPolicy.is_active.is_(True))
            .order_by(AutomationPolicy.updated_at.desc(), AutomationPolicy.id.desc())
        ).all()
        matches = [
            policy
            for policy in policies
            if self._matches(policy.account_id, account_id)
            and self._matches(policy.asset_id, asset_id)
            and self._matches(policy.strategy_playbook_id, strategy_playbook_id)
        ]
        if not matches:
            return EffectiveAutomationPolicy(
                id=None,
                user_id=user_id,
                account_id=account_id,
                asset_id=asset_id,
                strategy_playbook_id=strategy_playbook_id,
                automation_level="A0_READ_ONLY",
                max_notional_per_order=0,
                max_orders_per_day=0,
                requires_approval=True,
                allowed_actions=[],
                forbidden_actions=["LIVE_EXECUTION", "CONTROLLED_AUTO_EXECUTION"],
                is_active=True,
                source="default_read_only",
            )

        policy = max(matches, key=lambda item: self._specificity(item))
        if policy.automation_level == "A6_ADAPTIVE_AUTO_FUTURE":
            raise AutomationPolicyNotImplementedError("A6_ADAPTIVE_AUTO_FUTURE is not implemented")
        return self._effective_from_model(policy)

    def can_create_order_intent(self, policy: EffectiveAutomationPolicy, *, action: str = "CREATE_ORDER_INTENT") -> bool:
        return self._level_at_least(policy, "A3_ORDER_DRAFT") and self._action_allowed(policy, action)

    def can_create_order_draft(
        self,
        policy: EffectiveAutomationPolicy,
        *,
        action: str = "CREATE_ORDER_DRAFT",
        gates_passed: bool = False,
    ) -> bool:
        return self._level_at_least(policy, "A3_ORDER_DRAFT") and gates_passed and self._action_allowed(policy, action)

    def requires_human_approval(self, policy: EffectiveAutomationPolicy, *, action: str = "EXECUTE_PAPER") -> bool:
        if policy.automation_level == "A4_APPROVAL_EXECUTION":
            return True
        if policy.automation_level == "A5_CONTROLLED_AUTO" and action in CONTROLLED_AUTO_ACTIONS:
            return bool(policy.requires_approval)
        return True

    def can_execute_paper(
        self,
        policy: EffectiveAutomationPolicy,
        *,
        action: str = "EXECUTE_PAPER",
        human_approved: bool = False,
        gates_passed: bool = False,
    ) -> bool:
        if not self._level_at_least(policy, "A4_APPROVAL_EXECUTION") or not gates_passed or not self._action_allowed(policy, action):
            return False
        return human_approved

    def can_execute_live(
        self,
        policy: EffectiveAutomationPolicy,
        *,
        action: str = "EXECUTE_LIVE",
        human_approved: bool = False,
        gates_passed: bool = False,
        live_trading_enabled: bool = False,
    ) -> bool:
        if not live_trading_enabled:
            return False
        if not self._level_at_least(policy, "A4_APPROVAL_EXECUTION") or not gates_passed or not self._action_allowed(policy, action):
            return False
        return human_approved

    def can_execute_controlled_auto(
        self,
        policy: EffectiveAutomationPolicy,
        *,
        action: str,
        asset_id: str | None = None,
        account_id: str | None = None,
        gates_passed: bool = False,
        risk_budget_passed: bool = False,
        order_notional: float = 0,
    ) -> bool:
        allowed = (
            policy.automation_level == "A5_CONTROLLED_AUTO"
            and action in CONTROLLED_AUTO_ACTIONS
            and self._action_allowed(policy, action)
            and policy.asset_id is not None
            and policy.asset_id == asset_id
            and gates_passed
            and risk_budget_passed
            and self._respects_risk_budget(policy.user_id, account_id, asset_id, order_notional)
        )
        self._write_audit_log(
            action="automation_policy.controlled_auto_evaluated",
            entity_type="AutomationPolicy",
            entity_id=policy.id or "default",
            payload_json={
                "user_id": policy.user_id,
                "account_id": account_id,
                "asset_id": asset_id,
                "requested_action": action,
                "allowed": allowed,
                "gates_passed": gates_passed,
                "risk_budget_passed": risk_budget_passed,
            },
        )
        self.db.commit()
        return allowed

    def evaluate(
        self,
        *,
        user_id: str,
        account_id: str | None = None,
        asset_id: str | None = None,
        strategy_playbook_id: str | None = None,
        action: str = "CREATE_ORDER_INTENT",
        order_notional: float = 0,
        gates_passed: bool = False,
        risk_budget_passed: bool = False,
        human_approved: bool = False,
        live_trading_enabled: bool = False,
    ) -> AutomationPolicyEvaluation:
        policy = self.get_effective_policy(user_id, account_id, asset_id, strategy_playbook_id)
        can_intent = self.can_create_order_intent(policy, action="CREATE_ORDER_INTENT")
        can_draft = self.can_create_order_draft(policy, action="CREATE_ORDER_DRAFT", gates_passed=gates_passed)
        requires_approval = self.requires_human_approval(policy, action=action)
        can_paper = self.can_execute_paper(policy, action=action, human_approved=human_approved, gates_passed=gates_passed)
        can_live = self.can_execute_live(
            policy,
            action=action,
            human_approved=human_approved,
            gates_passed=gates_passed,
            live_trading_enabled=live_trading_enabled,
        )
        can_controlled = self.can_execute_controlled_auto(
            policy,
            action=action,
            asset_id=asset_id,
            account_id=account_id,
            gates_passed=gates_passed,
            risk_budget_passed=risk_budget_passed,
            order_notional=order_notional,
        )
        return AutomationPolicyEvaluation(
            policy=policy,
            action=action,
            can_create_order_intent=can_intent,
            can_create_order_draft=can_draft,
            requires_human_approval=requires_approval,
            can_execute_paper=can_paper,
            can_execute_live=can_live,
            can_execute_controlled_auto=can_controlled,
            blocking_reasons=self._blocking_reasons(
                policy=policy,
                action=action,
                asset_id=asset_id,
                gates_passed=gates_passed,
                risk_budget_passed=risk_budget_passed,
                live_trading_enabled=live_trading_enabled,
            ),
        )

    def _effective_from_model(self, policy: AutomationPolicy) -> EffectiveAutomationPolicy:
        return EffectiveAutomationPolicy(
            id=policy.id,
            user_id=policy.user_id,
            account_id=policy.account_id,
            asset_id=policy.asset_id,
            strategy_playbook_id=policy.strategy_playbook_id,
            automation_level=policy.automation_level,
            max_notional_per_order=float(policy.max_notional_per_order or 0),
            max_orders_per_day=policy.max_orders_per_day,
            requires_approval=policy.requires_approval,
            allowed_actions=list(policy.allowed_actions or []),
            forbidden_actions=list(policy.forbidden_actions or []),
            is_active=policy.is_active,
            source="stored_policy",
        )

    def _matches(self, policy_value: str | None, requested_value: str | None) -> bool:
        return policy_value is None or policy_value == requested_value

    def _specificity(self, policy: AutomationPolicy) -> tuple[int, str]:
        score = sum(1 for value in (policy.account_id, policy.asset_id, policy.strategy_playbook_id) if value is not None)
        return score, policy.updated_at.isoformat()

    def _level_at_least(self, policy: EffectiveAutomationPolicy, minimum: str) -> bool:
        return LEVEL_RANK.get(policy.automation_level, -1) >= LEVEL_RANK[minimum]

    def _action_allowed(self, policy: EffectiveAutomationPolicy, action: str) -> bool:
        if action in policy.forbidden_actions:
            return False
        return not policy.allowed_actions or action in policy.allowed_actions

    def _respects_risk_budget(
        self,
        user_id: str,
        account_id: str | None,
        asset_id: str | None,
        order_notional: float,
    ) -> bool:
        budgets = self.db.scalars(
            select(RiskBudget)
            .where(RiskBudget.user_id == user_id, (RiskBudget.account_id == account_id) | (RiskBudget.account_id.is_(None)))
            .order_by(RiskBudget.account_id.desc(), RiskBudget.updated_at.desc(), RiskBudget.id.desc())
        ).all()
        if not budgets:
            return False
        notional = Decimal(str(order_notional or 0))
        return any(notional <= Decimal(str(budget.max_order_notional or 0)) for budget in budgets)

    def _blocking_reasons(
        self,
        *,
        policy: EffectiveAutomationPolicy,
        action: str,
        asset_id: str | None,
        gates_passed: bool,
        risk_budget_passed: bool,
        live_trading_enabled: bool,
    ) -> list[str]:
        reasons: list[str] = []
        if policy.automation_level == "A0_READ_ONLY":
            reasons.append("default_read_only_policy")
        if action in policy.forbidden_actions:
            reasons.append("action_forbidden_by_policy")
        if policy.allowed_actions and action not in policy.allowed_actions:
            reasons.append("action_not_allowed_by_policy")
        if action in {"EXECUTE_LIVE", "LIVE_EXECUTION"} and not live_trading_enabled:
            reasons.append("live_trading_disabled")
        if action in CONTROLLED_AUTO_ACTIONS:
            if policy.automation_level != "A5_CONTROLLED_AUTO":
                reasons.append("controlled_auto_requires_a5")
            if policy.source == "default_read_only" or policy.asset_id is None or policy.asset_id != asset_id:
                reasons.append("controlled_auto_asset_not_whitelisted")
            if not gates_passed:
                reasons.append("controlled_auto_requires_gates_passed")
            if not risk_budget_passed:
                reasons.append("controlled_auto_requires_risk_budget_passed")
        return reasons

    def _write_audit_log(self, *, action: str, entity_type: str, entity_id: str, payload_json: dict[str, Any]) -> None:
        self.db.add(
            AuditLog(
                actor_type="system",
                actor_id="automation-policy-engine",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                payload_json=payload_json,
            )
        )
