"""v4 safe slices 7 8 9

Revision ID: 20260615_0015
Revises: 20260615_0014
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260615_0015"
down_revision: str | None = "20260615_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investment_ledger_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=True),
        sa.Column("quantity_delta", sa.Numeric(28, 10), nullable=False),
        sa.Column("cash_delta", sa.Numeric(28, 10), nullable=False),
        sa.Column("price", sa.Numeric(28, 10), nullable=True),
        sa.Column("fee_amount", sa.Numeric(28, 10), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(28, 10), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_investment_ledger_entries_user_id"), "investment_ledger_entries", ["user_id"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_account_id"), "investment_ledger_entries", ["account_id"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_asset_id"), "investment_ledger_entries", ["asset_id"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_source_type"), "investment_ledger_entries", ["source_type"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_source_id"), "investment_ledger_entries", ["source_id"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_entry_type"), "investment_ledger_entries", ["entry_type"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_occurred_at"), "investment_ledger_entries", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_investment_ledger_entries_status"), "investment_ledger_entries", ["status"], unique=False)
    op.create_index("ix_investment_ledger_source", "investment_ledger_entries", ["source_type", "source_id", "entry_type"], unique=False)
    op.create_index("ix_investment_ledger_account_asset", "investment_ledger_entries", ["account_id", "asset_id"], unique=False)

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("positions_checked", sa.Integer(), nullable=False),
        sa.Column("ledger_entries_checked", sa.Integer(), nullable=False),
        sa.Column("breaks_count", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("execution_available", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["source_snapshot_id"], ["data_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reconciliation_runs_user_id"), "reconciliation_runs", ["user_id"], unique=False)
    op.create_index(op.f("ix_reconciliation_runs_scope"), "reconciliation_runs", ["scope"], unique=False)
    op.create_index(op.f("ix_reconciliation_runs_status"), "reconciliation_runs", ["status"], unique=False)
    op.create_index(op.f("ix_reconciliation_runs_source_snapshot_id"), "reconciliation_runs", ["source_snapshot_id"], unique=False)
    op.create_index(op.f("ix_reconciliation_runs_checked_at"), "reconciliation_runs", ["checked_at"], unique=False)

    op.create_table(
        "reconciliation_breaks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reconciliation_run_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("break_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("expected_quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("observed_quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("delta_quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("expected_cash", sa.Numeric(28, 10), nullable=False),
        sa.Column("observed_cash", sa.Numeric(28, 10), nullable=False),
        sa.Column("delta_cash", sa.Numeric(28, 10), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["reconciliation_run_id"], ["reconciliation_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reconciliation_breaks_reconciliation_run_id"), "reconciliation_breaks", ["reconciliation_run_id"], unique=False)
    op.create_index(op.f("ix_reconciliation_breaks_account_id"), "reconciliation_breaks", ["account_id"], unique=False)
    op.create_index(op.f("ix_reconciliation_breaks_asset_id"), "reconciliation_breaks", ["asset_id"], unique=False)
    op.create_index(op.f("ix_reconciliation_breaks_break_type"), "reconciliation_breaks", ["break_type"], unique=False)
    op.create_index(op.f("ix_reconciliation_breaks_severity"), "reconciliation_breaks", ["severity"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reconciliation_breaks_severity"), table_name="reconciliation_breaks")
    op.drop_index(op.f("ix_reconciliation_breaks_break_type"), table_name="reconciliation_breaks")
    op.drop_index(op.f("ix_reconciliation_breaks_asset_id"), table_name="reconciliation_breaks")
    op.drop_index(op.f("ix_reconciliation_breaks_account_id"), table_name="reconciliation_breaks")
    op.drop_index(op.f("ix_reconciliation_breaks_reconciliation_run_id"), table_name="reconciliation_breaks")
    op.drop_table("reconciliation_breaks")
    op.drop_index(op.f("ix_reconciliation_runs_checked_at"), table_name="reconciliation_runs")
    op.drop_index(op.f("ix_reconciliation_runs_source_snapshot_id"), table_name="reconciliation_runs")
    op.drop_index(op.f("ix_reconciliation_runs_status"), table_name="reconciliation_runs")
    op.drop_index(op.f("ix_reconciliation_runs_scope"), table_name="reconciliation_runs")
    op.drop_index(op.f("ix_reconciliation_runs_user_id"), table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")
    op.drop_index("ix_investment_ledger_account_asset", table_name="investment_ledger_entries")
    op.drop_index("ix_investment_ledger_source", table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_status"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_occurred_at"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_entry_type"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_source_id"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_source_type"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_asset_id"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_account_id"), table_name="investment_ledger_entries")
    op.drop_index(op.f("ix_investment_ledger_entries_user_id"), table_name="investment_ledger_entries")
    op.drop_table("investment_ledger_entries")
