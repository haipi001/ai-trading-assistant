"""research to order traceability

Revision ID: 20260621_0018
Revises: 20260616_0017
Create Date: 2026-06-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260621_0018"
down_revision: str | None = "20260616_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("order_intents", sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("decision_gates", sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))


def downgrade() -> None:
    op.drop_column("decision_gates", "evidence_json")
    op.drop_column("order_intents", "evidence_json")
