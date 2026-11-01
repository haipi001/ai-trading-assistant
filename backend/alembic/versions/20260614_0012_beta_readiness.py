"""beta readiness

Revision ID: 20260614_0012
Revises: 20260613_0011
Create Date: 2026-06-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260614_0012"
down_revision: str | None = "20260613_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("permissions_json", sa.JSON(), nullable=False),
        sa.Column("onboarding_state_json", sa.JSON(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_user_accounts_user_id"), "user_accounts", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_accounts_role"), "user_accounts", ["role"], unique=False)
    op.create_index(op.f("ix_user_accounts_status"), "user_accounts", ["status"], unique=False)

    op.create_table(
        "secret_references",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("reference_key", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("storage_backend", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_secret_references_user_id"), "secret_references", ["user_id"], unique=False)
    op.create_index(op.f("ix_secret_references_reference_key"), "secret_references", ["reference_key"], unique=False)
    op.create_index(op.f("ix_secret_references_provider"), "secret_references", ["provider"], unique=False)
    op.create_index(op.f("ix_secret_references_status"), "secret_references", ["status"], unique=False)
    op.create_index("ix_secret_refs_user_reference", "secret_references", ["user_id", "reference_key"], unique=True)

    op.create_table(
        "operational_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_operational_events_user_id"), "operational_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_operational_events_event_type"), "operational_events", ["event_type"], unique=False)
    op.create_index(op.f("ix_operational_events_severity"), "operational_events", ["severity"], unique=False)
    op.create_index(op.f("ix_operational_events_source"), "operational_events", ["source"], unique=False)
    op.create_index(op.f("ix_operational_events_status"), "operational_events", ["status"], unique=False)
    op.create_index(op.f("ix_operational_events_request_id"), "operational_events", ["request_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_operational_events_request_id"), table_name="operational_events")
    op.drop_index(op.f("ix_operational_events_status"), table_name="operational_events")
    op.drop_index(op.f("ix_operational_events_source"), table_name="operational_events")
    op.drop_index(op.f("ix_operational_events_severity"), table_name="operational_events")
    op.drop_index(op.f("ix_operational_events_event_type"), table_name="operational_events")
    op.drop_index(op.f("ix_operational_events_user_id"), table_name="operational_events")
    op.drop_table("operational_events")

    op.drop_index("ix_secret_refs_user_reference", table_name="secret_references")
    op.drop_index(op.f("ix_secret_references_status"), table_name="secret_references")
    op.drop_index(op.f("ix_secret_references_provider"), table_name="secret_references")
    op.drop_index(op.f("ix_secret_references_reference_key"), table_name="secret_references")
    op.drop_index(op.f("ix_secret_references_user_id"), table_name="secret_references")
    op.drop_table("secret_references")

    op.drop_index(op.f("ix_user_accounts_status"), table_name="user_accounts")
    op.drop_index(op.f("ix_user_accounts_role"), table_name="user_accounts")
    op.drop_index(op.f("ix_user_accounts_user_id"), table_name="user_accounts")
    op.drop_table("user_accounts")
