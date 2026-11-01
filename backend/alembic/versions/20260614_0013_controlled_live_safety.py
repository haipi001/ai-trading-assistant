"""controlled live safety

Revision ID: 20260614_0013
Revises: 20260614_0012
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260614_0013"
down_revision: str | None = "20260614_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "live_execution_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("exchange_type", sa.String(length=64), nullable=False),
        sa.Column("api_key_ref", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_live_execution_configs_user_id"), "live_execution_configs", ["user_id"], unique=False)
    op.create_index(op.f("ix_live_execution_configs_exchange_type"), "live_execution_configs", ["exchange_type"], unique=False)
    op.create_index(op.f("ix_live_execution_configs_is_active"), "live_execution_configs", ["is_active"], unique=False)

    op.create_table(
        "broker_state_checks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("live_execution_config_id", sa.String(length=36), nullable=True),
        sa.Column("order_draft_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("connected", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["live_execution_config_id"], ["live_execution_configs.id"]),
        sa.ForeignKeyConstraint(["order_draft_id"], ["order_drafts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_broker_state_checks_live_execution_config_id"), "broker_state_checks", ["live_execution_config_id"], unique=False)
    op.create_index(op.f("ix_broker_state_checks_order_draft_id"), "broker_state_checks", ["order_draft_id"], unique=False)
    op.create_index(op.f("ix_broker_state_checks_status"), "broker_state_checks", ["status"], unique=False)

    op.create_table(
        "kill_switches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=True),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("engaged_by", sa.String(length=128), nullable=False),
        sa.Column("disengaged_by", sa.String(length=128), nullable=True),
        sa.Column("disengage_reason", sa.Text(), nullable=True),
        sa.Column("engaged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disengaged_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"]),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_kill_switches_account_id"), "kill_switches", ["account_id"], unique=False)
    op.create_index(op.f("ix_kill_switches_asset_id"), "kill_switches", ["asset_id"], unique=False)
    op.create_index(op.f("ix_kill_switches_disengaged_at"), "kill_switches", ["disengaged_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_kill_switches_disengaged_at"), table_name="kill_switches")
    op.drop_index(op.f("ix_kill_switches_asset_id"), table_name="kill_switches")
    op.drop_index(op.f("ix_kill_switches_account_id"), table_name="kill_switches")
    op.drop_table("kill_switches")

    op.drop_index(op.f("ix_broker_state_checks_status"), table_name="broker_state_checks")
    op.drop_index(op.f("ix_broker_state_checks_order_draft_id"), table_name="broker_state_checks")
    op.drop_index(op.f("ix_broker_state_checks_live_execution_config_id"), table_name="broker_state_checks")
    op.drop_table("broker_state_checks")

    op.drop_index(op.f("ix_live_execution_configs_is_active"), table_name="live_execution_configs")
    op.drop_index(op.f("ix_live_execution_configs_exchange_type"), table_name="live_execution_configs")
    op.drop_index(op.f("ix_live_execution_configs_user_id"), table_name="live_execution_configs")
    op.drop_table("live_execution_configs")
