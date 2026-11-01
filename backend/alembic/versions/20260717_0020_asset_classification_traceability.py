"""asset classification traceability

Revision ID: 20260717_0020
Revises: 20260717_0019
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260717_0020"
down_revision: str | None = "20260717_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.add_column(sa.Column("sector", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("industry", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("themes_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column("factor_tags_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
        batch_op.add_column(sa.Column("classification_source", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("classification_snapshot_id", sa.String(length=36), nullable=True))
        batch_op.create_index("ix_assets_sector", ["sector"], unique=False)
        batch_op.create_index("ix_assets_industry", ["industry"], unique=False)
        batch_op.create_index("ix_assets_classification_snapshot_id", ["classification_snapshot_id"], unique=False)
        batch_op.create_foreign_key("fk_assets_classification_snapshot_id", "data_snapshots", ["classification_snapshot_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("assets") as batch_op:
        batch_op.drop_constraint("fk_assets_classification_snapshot_id", type_="foreignkey")
        batch_op.drop_index("ix_assets_classification_snapshot_id")
        batch_op.drop_index("ix_assets_industry")
        batch_op.drop_index("ix_assets_sector")
        batch_op.drop_column("classification_snapshot_id")
        batch_op.drop_column("classification_source")
        batch_op.drop_column("factor_tags_json")
        batch_op.drop_column("themes_json")
        batch_op.drop_column("industry")
        batch_op.drop_column("sector")
