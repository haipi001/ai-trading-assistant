"""decision gate intervention level

Revision ID: 20260528_0003
Revises: 20260528_0002
Create Date: 2026-05-28
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260528_0003"
down_revision: Union[str, None] = "20260528_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "decision_gates",
        sa.Column("recommended_intervention_level", sa.String(length=32), server_default="SILENT_RECORD", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("decision_gates", "recommended_intervention_level")
