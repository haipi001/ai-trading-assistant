"""command bar models

Revision ID: 20260529_0004
Revises: 20260528_0003
Create Date: 2026-05-29
"""
from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260529_0004"
down_revision: Union[str, None] = "20260528_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "command_queries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("raw_query", sa.Text(), nullable=False),
        sa.Column("detected_intent", sa.String(length=64), nullable=False),
        sa.Column("required_tools", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_command_queries_user_id"), "command_queries", ["user_id"], unique=False)

    op.create_table(
        "command_tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("command_query_id", sa.String(length=36), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["command_query_id"], ["command_queries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_command_tool_calls_command_query_id"), "command_tool_calls", ["command_query_id"], unique=False)

    op.create_table(
        "command_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("command_query_id", sa.String(length=36), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("structured_result_json", sa.JSON(), nullable=False),
        sa.Column("data_sources_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["command_query_id"], ["command_queries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_command_results_command_query_id"), "command_results", ["command_query_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_command_results_command_query_id"), table_name="command_results")
    op.drop_table("command_results")
    op.drop_index(op.f("ix_command_tool_calls_command_query_id"), table_name="command_tool_calls")
    op.drop_table("command_tool_calls")
    op.drop_index(op.f("ix_command_queries_user_id"), table_name="command_queries")
    op.drop_table("command_queries")
