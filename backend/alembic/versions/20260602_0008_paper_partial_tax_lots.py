"""paper partial fills and tax lots

Revision ID: 20260602_0008
Revises: 20260601_0007
Create Date: 2026-06-02
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260602_0008"
down_revision: Union[str, None] = "20260601_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "executions",
        sa.Column("requested_quantity", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
    )
    op.add_column(
        "executions",
        sa.Column("cumulative_filled_quantity", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
    )
    op.add_column(
        "executions",
        sa.Column("remaining_quantity", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
    )
    op.add_column(
        "executions",
        sa.Column("proceeds_amount", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
    )
    op.add_column(
        "executions",
        sa.Column("cost_basis_amount", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
    )
    op.add_column(
        "executions",
        sa.Column("realized_pnl", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
    )

    op.create_table(
        "paper_tax_lots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("source_execution_id", sa.String(length=36), nullable=True),
        sa.Column("opened_order_draft_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("quantity_opened", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("quantity_remaining", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("average_cost", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("cost_basis_remaining", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["source_execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["opened_order_draft_id"], ["order_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_tax_lots_account_id"), "paper_tax_lots", ["account_id"], unique=False)
    op.create_index(op.f("ix_paper_tax_lots_asset_id"), "paper_tax_lots", ["asset_id"], unique=False)
    op.create_index(op.f("ix_paper_tax_lots_source_execution_id"), "paper_tax_lots", ["source_execution_id"], unique=False)
    op.create_index(op.f("ix_paper_tax_lots_opened_order_draft_id"), "paper_tax_lots", ["opened_order_draft_id"], unique=False)

    op.create_table(
        "paper_tax_lot_realizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("tax_lot_id", sa.String(length=36), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("proceeds_amount", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
        sa.Column("cost_basis_amount", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
        sa.Column("fee_allocated", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
        sa.Column("realized_pnl", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["tax_lot_id"], ["paper_tax_lots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_paper_tax_lot_realizations_execution_id"),
        "paper_tax_lot_realizations",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_paper_tax_lot_realizations_tax_lot_id"),
        "paper_tax_lot_realizations",
        ["tax_lot_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_paper_tax_lot_realizations_tax_lot_id"), table_name="paper_tax_lot_realizations")
    op.drop_index(op.f("ix_paper_tax_lot_realizations_execution_id"), table_name="paper_tax_lot_realizations")
    op.drop_table("paper_tax_lot_realizations")
    op.drop_index(op.f("ix_paper_tax_lots_opened_order_draft_id"), table_name="paper_tax_lots")
    op.drop_index(op.f("ix_paper_tax_lots_source_execution_id"), table_name="paper_tax_lots")
    op.drop_index(op.f("ix_paper_tax_lots_asset_id"), table_name="paper_tax_lots")
    op.drop_index(op.f("ix_paper_tax_lots_account_id"), table_name="paper_tax_lots")
    op.drop_table("paper_tax_lots")
    op.drop_column("executions", "realized_pnl")
    op.drop_column("executions", "cost_basis_amount")
    op.drop_column("executions", "proceeds_amount")
    op.drop_column("executions", "remaining_quantity")
    op.drop_column("executions", "cumulative_filled_quantity")
    op.drop_column("executions", "requested_quantity")
