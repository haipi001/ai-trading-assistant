"""readonly data sources and data snapshots

Revision ID: 20260601_0007
Revises: 20260601_0006
Create Date: 2026-06-01
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260601_0007"
down_revision: Union[str, None] = "20260601_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "data_source_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("credentials_ref", sa.String(length=255), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("last_health_status", sa.String(length=32), nullable=True),
        sa.Column("last_health_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_source_connections_provider"), "data_source_connections", ["provider"], unique=False)

    op.create_table(
        "data_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("snapshot_type", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_snapshots_snapshot_type"), "data_snapshots", ["snapshot_type"], unique=False)

    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("data_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("metric_type", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_snapshot_id"], ["data_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_quality_reports_data_snapshot_id"), "data_quality_reports", ["data_snapshot_id"], unique=False)
    op.create_index(op.f("ix_data_quality_reports_source"), "data_quality_reports", ["source"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_data_quality_reports_source"), table_name="data_quality_reports")
    op.drop_index(op.f("ix_data_quality_reports_data_snapshot_id"), table_name="data_quality_reports")
    op.drop_table("data_quality_reports")
    op.drop_index(op.f("ix_data_snapshots_snapshot_type"), table_name="data_snapshots")
    op.drop_table("data_snapshots")
    op.drop_index(op.f("ix_data_source_connections_provider"), table_name="data_source_connections")
    op.drop_table("data_source_connections")
