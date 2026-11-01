"""v4 safe slices 10 11 12

Revision ID: 20260615_0016
Revises: 20260615_0015
Create Date: 2026-06-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260615_0016"
down_revision: str | None = "20260615_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "statement_import_batches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("account_label", sa.String(length=255), nullable=True),
        sa.Column("statement_type", sa.String(length=64), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=True),
        sa.Column("raw_payload_hash", sa.String(length=64), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("imported_count", sa.Integer(), nullable=False),
        sa.Column("skipped_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary_json", sa.JSON(), nullable=False),
        sa.Column("execution_available", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_statement_import_batches_user_id"), "statement_import_batches", ["user_id"], unique=False)
    op.create_index(op.f("ix_statement_import_batches_provider"), "statement_import_batches", ["provider"], unique=False)
    op.create_index(op.f("ix_statement_import_batches_statement_type"), "statement_import_batches", ["statement_type"], unique=False)
    op.create_index(op.f("ix_statement_import_batches_source_ref"), "statement_import_batches", ["source_ref"], unique=False)
    op.create_index(op.f("ix_statement_import_batches_raw_payload_hash"), "statement_import_batches", ["raw_payload_hash"], unique=False)
    op.create_index(op.f("ix_statement_import_batches_status"), "statement_import_batches", ["status"], unique=False)

    op.create_table(
        "workflow_review_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("queue_item_id", sa.String(length=255), nullable=False),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assignee_id", sa.String(length=128), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("related_entity_type", sa.String(length=64), nullable=False),
        sa.Column("related_entity_id", sa.String(length=128), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workflow_review_tasks_user_id"), "workflow_review_tasks", ["user_id"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_queue_item_id"), "workflow_review_tasks", ["queue_item_id"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_item_type"), "workflow_review_tasks", ["item_type"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_priority"), "workflow_review_tasks", ["priority"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_status"), "workflow_review_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_assignee_id"), "workflow_review_tasks", ["assignee_id"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_due_at"), "workflow_review_tasks", ["due_at"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_related_entity_type"), "workflow_review_tasks", ["related_entity_type"], unique=False)
    op.create_index(op.f("ix_workflow_review_tasks_related_entity_id"), "workflow_review_tasks", ["related_entity_id"], unique=False)
    op.create_index("ix_workflow_review_tasks_user_status_due", "workflow_review_tasks", ["user_id", "status", "due_at"], unique=False)
    op.create_index("ix_workflow_review_tasks_queue_user", "workflow_review_tasks", ["queue_item_id", "user_id"], unique=False)

    op.create_table(
        "production_readiness_targets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("reference_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_production_readiness_targets_user_id"), "production_readiness_targets", ["user_id"], unique=False)
    op.create_index(op.f("ix_production_readiness_targets_target_type"), "production_readiness_targets", ["target_type"], unique=False)
    op.create_index(op.f("ix_production_readiness_targets_provider"), "production_readiness_targets", ["provider"], unique=False)
    op.create_index(op.f("ix_production_readiness_targets_reference_key"), "production_readiness_targets", ["reference_key"], unique=False)
    op.create_index(op.f("ix_production_readiness_targets_status"), "production_readiness_targets", ["status"], unique=False)
    op.create_index(
        "ix_production_targets_user_type_provider",
        "production_readiness_targets",
        ["user_id", "target_type", "provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_production_targets_user_type_provider", table_name="production_readiness_targets")
    op.drop_index(op.f("ix_production_readiness_targets_status"), table_name="production_readiness_targets")
    op.drop_index(op.f("ix_production_readiness_targets_reference_key"), table_name="production_readiness_targets")
    op.drop_index(op.f("ix_production_readiness_targets_provider"), table_name="production_readiness_targets")
    op.drop_index(op.f("ix_production_readiness_targets_target_type"), table_name="production_readiness_targets")
    op.drop_index(op.f("ix_production_readiness_targets_user_id"), table_name="production_readiness_targets")
    op.drop_table("production_readiness_targets")

    op.drop_index("ix_workflow_review_tasks_queue_user", table_name="workflow_review_tasks")
    op.drop_index("ix_workflow_review_tasks_user_status_due", table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_related_entity_id"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_related_entity_type"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_due_at"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_assignee_id"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_status"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_priority"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_item_type"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_queue_item_id"), table_name="workflow_review_tasks")
    op.drop_index(op.f("ix_workflow_review_tasks_user_id"), table_name="workflow_review_tasks")
    op.drop_table("workflow_review_tasks")

    op.drop_index(op.f("ix_statement_import_batches_status"), table_name="statement_import_batches")
    op.drop_index(op.f("ix_statement_import_batches_raw_payload_hash"), table_name="statement_import_batches")
    op.drop_index(op.f("ix_statement_import_batches_source_ref"), table_name="statement_import_batches")
    op.drop_index(op.f("ix_statement_import_batches_statement_type"), table_name="statement_import_batches")
    op.drop_index(op.f("ix_statement_import_batches_provider"), table_name="statement_import_batches")
    op.drop_index(op.f("ix_statement_import_batches_user_id"), table_name="statement_import_batches")
    op.drop_table("statement_import_batches")
