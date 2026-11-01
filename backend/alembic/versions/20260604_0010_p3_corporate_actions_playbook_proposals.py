"""Add P3 paper corporate actions and playbook proposals.

Revision ID: 20260604_0010
Revises: 20260602_0009
Create Date: 2026-06-04 00:10:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260604_0010"
down_revision: str | None = "20260602_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "paper_corporate_actions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity_before", sa.Numeric(28, 10), nullable=False),
        sa.Column("quantity_after", sa.Numeric(28, 10), nullable=False),
        sa.Column("cash_effect", sa.Numeric(28, 10), nullable=False),
        sa.Column("ratio", sa.Numeric(28, 10), nullable=True),
        sa.Column("amount_per_share", sa.Numeric(28, 10), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_paper_corporate_actions_account_id"), "paper_corporate_actions", ["account_id"])
    op.create_index(op.f("ix_paper_corporate_actions_asset_id"), "paper_corporate_actions", ["asset_id"])

    op.create_table(
        "playbook_update_proposals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_playbook_id", sa.String(length=36), nullable=True),
        sa.Column("proposal_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requires_user_approval", sa.Boolean(), nullable=False),
        sa.Column("reviewed_by", sa.String(length=128), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["strategy_playbook_id"], ["strategy_playbooks.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_playbook_update_proposals_source_id"), "playbook_update_proposals", ["source_id"])
    op.create_index(op.f("ix_playbook_update_proposals_strategy_playbook_id"), "playbook_update_proposals", ["strategy_playbook_id"])
    op.create_index(op.f("ix_playbook_update_proposals_user_id"), "playbook_update_proposals", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_playbook_update_proposals_user_id"), table_name="playbook_update_proposals")
    op.drop_index(op.f("ix_playbook_update_proposals_strategy_playbook_id"), table_name="playbook_update_proposals")
    op.drop_index(op.f("ix_playbook_update_proposals_source_id"), table_name="playbook_update_proposals")
    op.drop_table("playbook_update_proposals")
    op.drop_index(op.f("ix_paper_corporate_actions_asset_id"), table_name="paper_corporate_actions")
    op.drop_index(op.f("ix_paper_corporate_actions_account_id"), table_name="paper_corporate_actions")
    op.drop_table("paper_corporate_actions")
