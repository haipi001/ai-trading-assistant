"""daily use

Revision ID: 20260613_0011
Revises: 20260604_0010
Create Date: 2026-06-13
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260613_0011"
down_revision: Union[str, None] = "20260604_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("asset_id", sa.String(length=36), nullable=True),
        sa.Column("investment_thesis_id", sa.String(length=36), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("alert_rules_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["investment_thesis_id"], ["investment_theses.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_watchlist_items_user_id"), "watchlist_items", ["user_id"], unique=False)
    op.create_index(op.f("ix_watchlist_items_asset_id"), "watchlist_items", ["asset_id"], unique=False)
    op.create_index(op.f("ix_watchlist_items_investment_thesis_id"), "watchlist_items", ["investment_thesis_id"], unique=False)
    op.create_index(op.f("ix_watchlist_items_symbol"), "watchlist_items", ["symbol"], unique=False)
    op.create_index("ix_watchlist_user_symbol", "watchlist_items", ["user_id", "symbol"], unique=False)

    op.create_table(
        "reminders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("reminder_type", sa.String(length=64), nullable=False),
        sa.Column("related_entity_type", sa.String(length=64), nullable=True),
        sa.Column("related_entity_id", sa.String(length=128), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recurrence_json", sa.JSON(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reminders_user_id"), "reminders", ["user_id"], unique=False)
    op.create_index(op.f("ix_reminders_reminder_type"), "reminders", ["reminder_type"], unique=False)
    op.create_index(op.f("ix_reminders_related_entity_id"), "reminders", ["related_entity_id"], unique=False)
    op.create_index(op.f("ix_reminders_due_at"), "reminders", ["due_at"], unique=False)
    op.create_index(op.f("ix_reminders_status"), "reminders", ["status"], unique=False)
    op.create_index("ix_reminders_user_status_due", "reminders", ["user_id", "status", "due_at"], unique=False)

    op.create_table(
        "local_user_configs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("config_key", sa.String(length=128), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_local_user_configs_user_id"), "local_user_configs", ["user_id"], unique=False)
    op.create_index(op.f("ix_local_user_configs_config_key"), "local_user_configs", ["config_key"], unique=False)
    op.create_index("ix_local_user_configs_user_key", "local_user_configs", ["user_id", "config_key"], unique=True)

    op.create_table(
        "export_artifacts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("export_type", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_export_artifacts_user_id"), "export_artifacts", ["user_id"], unique=False)
    op.create_index(op.f("ix_export_artifacts_export_type"), "export_artifacts", ["export_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_export_artifacts_export_type"), table_name="export_artifacts")
    op.drop_index(op.f("ix_export_artifacts_user_id"), table_name="export_artifacts")
    op.drop_table("export_artifacts")

    op.drop_index("ix_local_user_configs_user_key", table_name="local_user_configs")
    op.drop_index(op.f("ix_local_user_configs_config_key"), table_name="local_user_configs")
    op.drop_index(op.f("ix_local_user_configs_user_id"), table_name="local_user_configs")
    op.drop_table("local_user_configs")

    op.drop_index("ix_reminders_user_status_due", table_name="reminders")
    op.drop_index(op.f("ix_reminders_status"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_due_at"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_related_entity_id"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_reminder_type"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_user_id"), table_name="reminders")
    op.drop_table("reminders")

    op.drop_index("ix_watchlist_user_symbol", table_name="watchlist_items")
    op.drop_index(op.f("ix_watchlist_items_symbol"), table_name="watchlist_items")
    op.drop_index(op.f("ix_watchlist_items_investment_thesis_id"), table_name="watchlist_items")
    op.drop_index(op.f("ix_watchlist_items_asset_id"), table_name="watchlist_items")
    op.drop_index(op.f("ix_watchlist_items_user_id"), table_name="watchlist_items")
    op.drop_table("watchlist_items")
