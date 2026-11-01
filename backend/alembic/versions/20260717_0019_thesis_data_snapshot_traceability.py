"""thesis data snapshot traceability

Revision ID: 20260717_0019
Revises: 20260621_0018
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260717_0019"
down_revision: str | None = "20260621_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("investment_theses") as batch_op:
        batch_op.add_column(sa.Column("data_snapshot_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_investment_theses_data_snapshot_id", ["data_snapshot_id"], unique=False)
        batch_op.create_foreign_key("fk_investment_theses_data_snapshot_id", "data_snapshots", ["data_snapshot_id"], ["id"])
    with op.batch_alter_table("thesis_checkpoints") as batch_op:
        batch_op.add_column(sa.Column("data_snapshot_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_thesis_checkpoints_data_snapshot_id", ["data_snapshot_id"], unique=False)
        batch_op.create_foreign_key("fk_thesis_checkpoints_data_snapshot_id", "data_snapshots", ["data_snapshot_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("thesis_checkpoints") as batch_op:
        batch_op.drop_constraint("fk_thesis_checkpoints_data_snapshot_id", type_="foreignkey")
        batch_op.drop_index("ix_thesis_checkpoints_data_snapshot_id")
        batch_op.drop_column("data_snapshot_id")
    with op.batch_alter_table("investment_theses") as batch_op:
        batch_op.drop_constraint("fk_investment_theses_data_snapshot_id", type_="foreignkey")
        batch_op.drop_index("ix_investment_theses_data_snapshot_id")
        batch_op.drop_column("data_snapshot_id")
