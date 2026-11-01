"""paper execution portfolio and post trade reviews

Revision ID: 20260601_0006
Revises: 20260529_0005
Create Date: 2026-06-01
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260601_0006"
down_revision: Union[str, None] = "20260529_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("executions", sa.Column("position_id", sa.String(length=36), nullable=True))
    op.add_column("executions", sa.Column("fill_notional", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("fee_amount", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("slippage_amount", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"))
    op.add_column("executions", sa.Column("cash_effect", sa.Numeric(precision=28, scale=10), nullable=False, server_default="0"))
    op.create_index(op.f("ix_executions_position_id"), "executions", ["position_id"], unique=False)

    op.create_table(
        "post_trade_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("trade_journal_entry_id", sa.String(length=36), nullable=False),
        sa.Column("order_draft_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prompt_json", sa.JSON(), nullable=False),
        sa.Column("review_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"]),
        sa.ForeignKeyConstraint(["trade_journal_entry_id"], ["trade_journal_entries.id"]),
        sa.ForeignKeyConstraint(["order_draft_id"], ["order_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_post_trade_reviews_execution_id"), "post_trade_reviews", ["execution_id"], unique=False)
    op.create_index(
        op.f("ix_post_trade_reviews_trade_journal_entry_id"),
        "post_trade_reviews",
        ["trade_journal_entry_id"],
        unique=False,
    )
    op.create_index(op.f("ix_post_trade_reviews_order_draft_id"), "post_trade_reviews", ["order_draft_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_post_trade_reviews_order_draft_id"), table_name="post_trade_reviews")
    op.drop_index(op.f("ix_post_trade_reviews_trade_journal_entry_id"), table_name="post_trade_reviews")
    op.drop_index(op.f("ix_post_trade_reviews_execution_id"), table_name="post_trade_reviews")
    op.drop_table("post_trade_reviews")
    op.drop_index(op.f("ix_executions_position_id"), table_name="executions")
    op.drop_column("executions", "cash_effect")
    op.drop_column("executions", "slippage_amount")
    op.drop_column("executions", "fee_amount")
    op.drop_column("executions", "fill_notional")
    op.drop_column("executions", "position_id")
