"""restore ORM and migration schema parity

Revision ID: 20260717_0022
Revises: 20260717_0021
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from alembic import context


revision: str = "20260717_0022"
down_revision: str | None = "20260717_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ORDER_INTENT_FOREIGN_KEYS = (
    ("fk_order_intents_investment_thesis_id", "investment_theses", "investment_thesis_id"),
    ("fk_order_intents_strategy_playbook_id", "strategy_playbooks", "strategy_playbook_id"),
    ("fk_order_intents_automation_policy_id", "automation_policies", "automation_policy_id"),
    ("fk_order_intents_source_signal_id", "signals", "source_signal_id"),
)


def upgrade() -> None:
    bind = op.get_bind()
    offline = context.is_offline_mode()
    if not offline:
        duplicate = bind.execute(
            sa.text(
                "SELECT user_id FROM user_accounts GROUP BY user_id "
                "HAVING COUNT(*) > 1 LIMIT 1"
            )
        ).first()
        if duplicate is not None:
            raise RuntimeError("user_accounts contains duplicate user_id values; resolve them before migration")

    with op.batch_alter_table("user_accounts") as batch_op:
        batch_op.drop_index("ix_user_accounts_user_id")
        batch_op.create_index("ix_user_accounts_user_id", ["user_id"], unique=True)

    existing_order_intent_foreign_keys = set()
    existing_execution_foreign_keys = set()
    if not offline:
        inspector = sa.inspect(bind)
        existing_order_intent_foreign_keys = {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("order_intents")
            if foreign_key.get("name")
        }
        existing_execution_foreign_keys = {
            foreign_key["name"]
            for foreign_key in inspector.get_foreign_keys("executions")
            if foreign_key.get("name")
        }

    missing_order_intent_foreign_keys = [
        foreign_key
        for foreign_key in ORDER_INTENT_FOREIGN_KEYS
        if foreign_key[0] not in existing_order_intent_foreign_keys
    ]
    if missing_order_intent_foreign_keys:
        with op.batch_alter_table("order_intents") as batch_op:
            for constraint_name, target_table, column_name in missing_order_intent_foreign_keys:
                batch_op.create_foreign_key(constraint_name, target_table, [column_name], ["id"])

    if "fk_executions_position_id" not in existing_execution_foreign_keys:
        with op.batch_alter_table("executions") as batch_op:
            batch_op.create_foreign_key("fk_executions_position_id", "positions", ["position_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("executions") as batch_op:
        batch_op.drop_constraint("fk_executions_position_id", type_="foreignkey")

    # PostgreSQL already received these constraints in revision 20260528_0002.
    # Revision 0022 only restores them for SQLite, where that earlier revision
    # intentionally skipped foreign-key creation.
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("order_intents") as batch_op:
            for constraint_name, _target_table, _column_name in reversed(ORDER_INTENT_FOREIGN_KEYS):
                batch_op.drop_constraint(constraint_name, type_="foreignkey")

    with op.batch_alter_table("user_accounts") as batch_op:
        batch_op.drop_index("ix_user_accounts_user_id")
        batch_op.create_index("ix_user_accounts_user_id", ["user_id"], unique=False)
