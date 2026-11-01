"""v3 self logic domain models

Revision ID: 20260528_0002
Revises: 20260528_0001
Create Date: 2026-05-28
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260528_0002"
down_revision: Union[str, None] = "20260528_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_constitutions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("investment_style", sa.String(length=128), nullable=False),
        sa.Column("allowed_markets", sa.JSON(), nullable=False),
        sa.Column("forbidden_assets", sa.JSON(), nullable=False),
        sa.Column("forbidden_actions", sa.JSON(), nullable=False),
        sa.Column("max_single_position_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_asset_class_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_crypto_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_single_exchange_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_daily_loss_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_monthly_drawdown_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("leverage_allowed", sa.Boolean(), nullable=False),
        sa.Column("derivatives_allowed", sa.Boolean(), nullable=False),
        sa.Column("auto_execution_allowed", sa.Boolean(), nullable=False),
        sa.Column("human_approval_required", sa.Boolean(), nullable=False),
        sa.Column("cooldown_rules_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_investment_constitutions_user_id"), "investment_constitutions", ["user_id"], unique=False)

    op.create_table(
        "risk_budgets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("constitution_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("asset_class", sa.String(length=64), nullable=False),
        sa.Column("max_allocation_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_loss_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("max_order_notional", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("max_leverage", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column("rebalance_threshold_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["constitution_id"], ["investment_constitutions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_risk_budgets_account_id"), "risk_budgets", ["account_id"], unique=False)
    op.create_index(op.f("ix_risk_budgets_constitution_id"), "risk_budgets", ["constitution_id"], unique=False)
    op.create_index(op.f("ix_risk_budgets_user_id"), "risk_budgets", ["user_id"], unique=False)

    op.create_table(
        "strategy_playbooks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("strategy_type", sa.String(length=64), nullable=False),
        sa.Column("applicable_markets", sa.JSON(), nullable=False),
        sa.Column("applicable_assets", sa.JSON(), nullable=False),
        sa.Column("entry_conditions_json", sa.JSON(), nullable=False),
        sa.Column("exit_conditions_json", sa.JSON(), nullable=False),
        sa.Column("risk_rules_json", sa.JSON(), nullable=False),
        sa.Column("automation_level", sa.String(length=32), nullable=False),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategy_playbooks_user_id"), "strategy_playbooks", ["user_id"], unique=False)

    op.create_table(
        "investment_theses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("strategy_playbook_id", sa.String(length=36), nullable=True),
        sa.Column("entry_reason", sa.Text(), nullable=False),
        sa.Column("key_drivers_json", sa.JSON(), nullable=False),
        sa.Column("invalidation_conditions_json", sa.JSON(), nullable=False),
        sa.Column("expected_horizon", sa.String(length=64), nullable=False),
        sa.Column("target_condition", sa.Text(), nullable=False),
        sa.Column("max_loss_tolerance_pct", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("position_plan_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"]),
        sa.ForeignKeyConstraint(["strategy_playbook_id"], ["strategy_playbooks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_investment_theses_account_id"), "investment_theses", ["account_id"], unique=False)
    op.create_index(op.f("ix_investment_theses_asset_id"), "investment_theses", ["asset_id"], unique=False)
    op.create_index(op.f("ix_investment_theses_position_id"), "investment_theses", ["position_id"], unique=False)
    op.create_index(op.f("ix_investment_theses_strategy_playbook_id"), "investment_theses", ["strategy_playbook_id"], unique=False)
    op.create_index(op.f("ix_investment_theses_user_id"), "investment_theses", ["user_id"], unique=False)

    op.create_table(
        "thesis_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thesis_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_type", sa.String(length=64), nullable=False),
        sa.Column("observed_facts_json", sa.JSON(), nullable=False),
        sa.Column("supports_thesis", sa.Boolean(), nullable=False),
        sa.Column("weakens_thesis", sa.Boolean(), nullable=False),
        sa.Column("invalidates_thesis", sa.Boolean(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["thesis_id"], ["investment_theses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_thesis_checkpoints_thesis_id"), "thesis_checkpoints", ["thesis_id"], unique=False)

    op.create_table(
        "automation_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("strategy_playbook_id", sa.String(length=36), nullable=True),
        sa.Column("automation_level", sa.String(length=32), nullable=False),
        sa.Column("max_notional_per_order", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("max_orders_per_day", sa.Integer(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("allowed_actions", sa.JSON(), nullable=False),
        sa.Column("forbidden_actions", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["strategy_playbook_id"], ["strategy_playbooks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_automation_policies_account_id"), "automation_policies", ["account_id"], unique=False)
    op.create_index(op.f("ix_automation_policies_asset_id"), "automation_policies", ["asset_id"], unique=False)
    op.create_index(op.f("ix_automation_policies_strategy_playbook_id"), "automation_policies", ["strategy_playbook_id"], unique=False)
    op.create_index(op.f("ix_automation_policies_user_id"), "automation_policies", ["user_id"], unique=False)

    op.create_table(
        "behavior_patterns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("pattern_type", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_behavior_patterns_asset_id"), "behavior_patterns", ["asset_id"], unique=False)
    op.create_index(op.f("ix_behavior_patterns_user_id"), "behavior_patterns", ["user_id"], unique=False)

    op.create_table(
        "workflow_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("current_state", sa.String(length=64), nullable=False),
        sa.Column("previous_state", sa.String(length=64), nullable=True),
        sa.Column("transition_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_states_entity_id"), "workflow_states", ["entity_id"], unique=False)

    op.create_table(
        "monthly_decision_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_trades", sa.Integer(), nullable=False),
        sa.Column("thesis_aligned_trades", sa.Integer(), nullable=False),
        sa.Column("thesis_violating_trades", sa.Integer(), nullable=False),
        sa.Column("impulsive_trades", sa.Integer(), nullable=False),
        sa.Column("blocked_trades", sa.Integer(), nullable=False),
        sa.Column("bypassed_warnings", sa.Integer(), nullable=False),
        sa.Column("planned_trade_pnl", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("impulsive_trade_pnl", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("overtrading_cost", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("top_behavior_patterns_json", sa.JSON(), nullable=False),
        sa.Column("recommended_rule_updates_json", sa.JSON(), nullable=False),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_monthly_decision_reviews_user_id"), "monthly_decision_reviews", ["user_id"], unique=False)

    op.add_column("order_intents", sa.Column("investment_thesis_id", sa.String(length=36), nullable=True))
    op.add_column("order_intents", sa.Column("strategy_playbook_id", sa.String(length=36), nullable=True))
    op.add_column("order_intents", sa.Column("automation_policy_id", sa.String(length=36), nullable=True))
    op.add_column("order_intents", sa.Column("source_signal_id", sa.String(length=36), nullable=True))
    op.add_column("order_intents", sa.Column("user_rationale", sa.Text(), nullable=True))
    op.create_index(op.f("ix_order_intents_investment_thesis_id"), "order_intents", ["investment_thesis_id"], unique=False)
    op.create_index(op.f("ix_order_intents_strategy_playbook_id"), "order_intents", ["strategy_playbook_id"], unique=False)
    op.create_index(op.f("ix_order_intents_automation_policy_id"), "order_intents", ["automation_policy_id"], unique=False)
    op.create_index(op.f("ix_order_intents_source_signal_id"), "order_intents", ["source_signal_id"], unique=False)
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key("fk_order_intents_investment_thesis_id", "order_intents", "investment_theses", ["investment_thesis_id"], ["id"])
        op.create_foreign_key("fk_order_intents_strategy_playbook_id", "order_intents", "strategy_playbooks", ["strategy_playbook_id"], ["id"])
        op.create_foreign_key("fk_order_intents_automation_policy_id", "order_intents", "automation_policies", ["automation_policy_id"], ["id"])
        op.create_foreign_key("fk_order_intents_source_signal_id", "order_intents", "signals", ["source_signal_id"], ["id"])

    op.add_column("order_drafts", sa.Column("behavior_status", sa.String(length=32), server_default="pending", nullable=False))
    op.add_column("order_drafts", sa.Column("decision_gate_results", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("order_drafts", sa.Column("approval_policy", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))

    op.create_table(
        "thesis_violations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thesis_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("related_order_intent_id", sa.String(length=36), nullable=True),
        sa.Column("violation_type", sa.String(length=64), nullable=False),
        sa.Column("prior_user_statement", sa.Text(), nullable=False),
        sa.Column("current_action", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("intervention_level", sa.String(length=32), nullable=False),
        sa.Column("resolved_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["related_order_intent_id"], ["order_intents.id"]),
        sa.ForeignKeyConstraint(["thesis_id"], ["investment_theses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_thesis_violations_related_order_intent_id"), "thesis_violations", ["related_order_intent_id"], unique=False)
    op.create_index(op.f("ix_thesis_violations_thesis_id"), "thesis_violations", ["thesis_id"], unique=False)
    op.create_index(op.f("ix_thesis_violations_user_id"), "thesis_violations", ["user_id"], unique=False)

    op.create_table(
        "decision_gates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_intent_id", sa.String(length=36), nullable=True),
        sa.Column("gate_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=6), nullable=True),
        sa.Column("blocking_reasons_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("evaluator", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_decision_gates_order_intent_id"), "decision_gates", ["order_intent_id"], unique=False)

    op.create_table(
        "behavior_interventions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("pattern_id", sa.String(length=36), nullable=True),
        sa.Column("order_intent_id", sa.String(length=36), nullable=True),
        sa.Column("intervention_level", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("user_response", sa.Text(), nullable=True),
        sa.Column("bypassed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_intent_id"], ["order_intents.id"]),
        sa.ForeignKeyConstraint(["pattern_id"], ["behavior_patterns.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_behavior_interventions_order_intent_id"), "behavior_interventions", ["order_intent_id"], unique=False)
    op.create_index(op.f("ix_behavior_interventions_pattern_id"), "behavior_interventions", ["pattern_id"], unique=False)
    op.create_index(op.f("ix_behavior_interventions_user_id"), "behavior_interventions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_behavior_interventions_user_id"), table_name="behavior_interventions")
    op.drop_index(op.f("ix_behavior_interventions_pattern_id"), table_name="behavior_interventions")
    op.drop_index(op.f("ix_behavior_interventions_order_intent_id"), table_name="behavior_interventions")
    op.drop_table("behavior_interventions")
    op.drop_index(op.f("ix_decision_gates_order_intent_id"), table_name="decision_gates")
    op.drop_table("decision_gates")
    op.drop_index(op.f("ix_thesis_violations_user_id"), table_name="thesis_violations")
    op.drop_index(op.f("ix_thesis_violations_thesis_id"), table_name="thesis_violations")
    op.drop_index(op.f("ix_thesis_violations_related_order_intent_id"), table_name="thesis_violations")
    op.drop_table("thesis_violations")
    op.drop_column("order_drafts", "approval_policy")
    op.drop_column("order_drafts", "decision_gate_results")
    op.drop_column("order_drafts", "behavior_status")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_order_intents_source_signal_id", "order_intents", type_="foreignkey")
        op.drop_constraint("fk_order_intents_automation_policy_id", "order_intents", type_="foreignkey")
        op.drop_constraint("fk_order_intents_strategy_playbook_id", "order_intents", type_="foreignkey")
        op.drop_constraint("fk_order_intents_investment_thesis_id", "order_intents", type_="foreignkey")
    op.drop_index(op.f("ix_order_intents_source_signal_id"), table_name="order_intents")
    op.drop_index(op.f("ix_order_intents_automation_policy_id"), table_name="order_intents")
    op.drop_index(op.f("ix_order_intents_strategy_playbook_id"), table_name="order_intents")
    op.drop_index(op.f("ix_order_intents_investment_thesis_id"), table_name="order_intents")
    op.drop_column("order_intents", "user_rationale")
    op.drop_column("order_intents", "source_signal_id")
    op.drop_column("order_intents", "automation_policy_id")
    op.drop_column("order_intents", "strategy_playbook_id")
    op.drop_column("order_intents", "investment_thesis_id")
    op.drop_index(op.f("ix_monthly_decision_reviews_user_id"), table_name="monthly_decision_reviews")
    op.drop_table("monthly_decision_reviews")
    op.drop_index(op.f("ix_workflow_states_entity_id"), table_name="workflow_states")
    op.drop_table("workflow_states")
    op.drop_index(op.f("ix_behavior_patterns_user_id"), table_name="behavior_patterns")
    op.drop_index(op.f("ix_behavior_patterns_asset_id"), table_name="behavior_patterns")
    op.drop_table("behavior_patterns")
    op.drop_index(op.f("ix_automation_policies_user_id"), table_name="automation_policies")
    op.drop_index(op.f("ix_automation_policies_strategy_playbook_id"), table_name="automation_policies")
    op.drop_index(op.f("ix_automation_policies_asset_id"), table_name="automation_policies")
    op.drop_index(op.f("ix_automation_policies_account_id"), table_name="automation_policies")
    op.drop_table("automation_policies")
    op.drop_index(op.f("ix_thesis_checkpoints_thesis_id"), table_name="thesis_checkpoints")
    op.drop_table("thesis_checkpoints")
    op.drop_index(op.f("ix_investment_theses_user_id"), table_name="investment_theses")
    op.drop_index(op.f("ix_investment_theses_strategy_playbook_id"), table_name="investment_theses")
    op.drop_index(op.f("ix_investment_theses_position_id"), table_name="investment_theses")
    op.drop_index(op.f("ix_investment_theses_asset_id"), table_name="investment_theses")
    op.drop_index(op.f("ix_investment_theses_account_id"), table_name="investment_theses")
    op.drop_table("investment_theses")
    op.drop_index(op.f("ix_strategy_playbooks_user_id"), table_name="strategy_playbooks")
    op.drop_table("strategy_playbooks")
    op.drop_index(op.f("ix_risk_budgets_user_id"), table_name="risk_budgets")
    op.drop_index(op.f("ix_risk_budgets_constitution_id"), table_name="risk_budgets")
    op.drop_index(op.f("ix_risk_budgets_account_id"), table_name="risk_budgets")
    op.drop_table("risk_budgets")
    op.drop_index(op.f("ix_investment_constitutions_user_id"), table_name="investment_constitutions")
    op.drop_table("investment_constitutions")
