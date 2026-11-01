"""scheduled jobs

Revision ID: 20260602_0009
Revises: 20260602_0008
Create Date: 2026-06-02
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260602_0009"
down_revision: Union[str, None] = "20260602_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scheduled_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("schedule_json", sa.JSON(), nullable=False),
        sa.Column("target_json", sa.JSON(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=32), nullable=True),
        sa.Column("last_run_summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_scheduled_jobs_job_type"), "scheduled_jobs", ["job_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scheduled_jobs_job_type"), table_name="scheduled_jobs")
    op.drop_table("scheduled_jobs")
