"""tenant ownership for legacy single-user resources

Revision ID: 20260717_0021
Revises: 20260717_0020
Create Date: 2026-07-17
"""

from collections.abc import Sequence
import os

import sqlalchemy as sa
from alembic import op


revision: str = "20260717_0021"
down_revision: str | None = "20260717_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TENANT_TABLES = (
    "accounts",
    "agent_runs",
    "approvals",
    "audit_logs",
    "broker_state_checks",
    "command_results",
    "command_tool_calls",
    "data_catalog_entries",
    "data_quality_reports",
    "data_snapshots",
    "data_source_connections",
    "decision_gates",
    "executions",
    "kill_switches",
    "order_drafts",
    "order_intents",
    "paper_corporate_actions",
    "paper_tax_lot_realizations",
    "paper_tax_lots",
    "portfolio_snapshots",
    "positions",
    "protocol_positions",
    "reconciliation_breaks",
    "research_reports",
    "risk_checks",
    "scheduled_jobs",
    "signals",
    "strategy_rules",
    "thesis_checkpoints",
    "token_allowances",
    "token_balances",
    "trade_journal_entries",
    "wallet_transfers",
    "workflow_states",
)


def _legacy_tenant_id() -> str:
    value = os.getenv("LEGACY_TENANT_USER_ID", "default-user").strip()
    if not value or len(value) > 128:
        raise RuntimeError("LEGACY_TENANT_USER_ID must contain 1-128 characters")
    return value


def upgrade() -> None:
    legacy_tenant_id = _legacy_tenant_id()
    bind = op.get_bind()
    for table_name in TENANT_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(sa.Column("user_id", sa.String(length=128), nullable=True))
        bind.execute(
            sa.text(f'UPDATE "{table_name}" SET user_id = :tenant_id WHERE user_id IS NULL'),
            {"tenant_id": legacy_tenant_id},
        )
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column("user_id", existing_type=sa.String(length=128), nullable=False)
            batch_op.create_index(f"ix_{table_name}_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    for table_name in reversed(TENANT_TABLES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_index(f"ix_{table_name}_user_id")
            batch_op.drop_column("user_id")
