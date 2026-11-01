"""csv import data catalog

Revision ID: 20260615_0014
Revises: 20260614_0013
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260615_0014"
down_revision: str | None = "20260614_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "data_catalog_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_type", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("data_snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("quality_report_id", sa.String(length=36), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("quality_status", sa.String(length=32), nullable=False),
        sa.Column("usable_for_trading", sa.Boolean(), nullable=False),
        sa.Column("lineage_json", sa.JSON(), nullable=False),
        sa.Column("contract_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["data_snapshot_id"], ["data_snapshots.id"]),
        sa.ForeignKeyConstraint(["quality_report_id"], ["data_quality_reports.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_catalog_entries_dataset_type"), "data_catalog_entries", ["dataset_type"], unique=False)
    op.create_index(op.f("ix_data_catalog_entries_source"), "data_catalog_entries", ["source"], unique=False)
    op.create_index(op.f("ix_data_catalog_entries_data_snapshot_id"), "data_catalog_entries", ["data_snapshot_id"], unique=False)
    op.create_index(op.f("ix_data_catalog_entries_quality_report_id"), "data_catalog_entries", ["quality_report_id"], unique=False)
    op.create_index(op.f("ix_data_catalog_entries_quality_status"), "data_catalog_entries", ["quality_status"], unique=False)
    op.create_index(op.f("ix_data_catalog_entries_usable_for_trading"), "data_catalog_entries", ["usable_for_trading"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_data_catalog_entries_usable_for_trading"), table_name="data_catalog_entries")
    op.drop_index(op.f("ix_data_catalog_entries_quality_status"), table_name="data_catalog_entries")
    op.drop_index(op.f("ix_data_catalog_entries_quality_report_id"), table_name="data_catalog_entries")
    op.drop_index(op.f("ix_data_catalog_entries_data_snapshot_id"), table_name="data_catalog_entries")
    op.drop_index(op.f("ix_data_catalog_entries_source"), table_name="data_catalog_entries")
    op.drop_index(op.f("ix_data_catalog_entries_dataset_type"), table_name="data_catalog_entries")
    op.drop_table("data_catalog_entries")
