"""route parity safe lab

Revision ID: 20260616_0017
Revises: 20260615_0016
Create Date: 2026-06-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260616_0017"
down_revision: str | None = "20260615_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("strategy_playbook_id", sa.String(length=36), nullable=False),
        sa.Column("rule_type", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("actions_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["strategy_playbook_id"], ["strategy_playbooks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_strategy_rules_strategy_playbook_id"), "strategy_rules", ["strategy_playbook_id"], unique=False)
    op.create_index(op.f("ix_strategy_rules_rule_type"), "strategy_rules", ["rule_type"], unique=False)
    op.create_index(op.f("ix_strategy_rules_priority"), "strategy_rules", ["priority"], unique=False)
    op.create_index(op.f("ix_strategy_rules_is_active"), "strategy_rules", ["is_active"], unique=False)
    op.create_index("ix_strategy_rules_playbook_priority", "strategy_rules", ["strategy_playbook_id", "priority"], unique=False)

    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("strategy_playbook_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Numeric(28, 10), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("parameters_json", sa.JSON(), nullable=False),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["strategy_playbook_id"], ["strategy_playbooks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_backtest_runs_user_id"), "backtest_runs", ["user_id"], unique=False)
    op.create_index(op.f("ix_backtest_runs_strategy_playbook_id"), "backtest_runs", ["strategy_playbook_id"], unique=False)
    op.create_index(op.f("ix_backtest_runs_status"), "backtest_runs", ["status"], unique=False)
    op.create_index("ix_backtest_runs_playbook_created", "backtest_runs", ["strategy_playbook_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_backtest_runs_playbook_created", table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_status"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_strategy_playbook_id"), table_name="backtest_runs")
    op.drop_index(op.f("ix_backtest_runs_user_id"), table_name="backtest_runs")
    op.drop_table("backtest_runs")

    op.drop_index("ix_strategy_rules_playbook_priority", table_name="strategy_rules")
    op.drop_index(op.f("ix_strategy_rules_is_active"), table_name="strategy_rules")
    op.drop_index(op.f("ix_strategy_rules_priority"), table_name="strategy_rules")
    op.drop_index(op.f("ix_strategy_rules_rule_type"), table_name="strategy_rules")
    op.drop_index(op.f("ix_strategy_rules_strategy_playbook_id"), table_name="strategy_rules")
    op.drop_table("strategy_rules")
