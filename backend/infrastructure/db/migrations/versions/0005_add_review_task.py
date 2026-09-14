"""add review_task table

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-14 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_task",
        sa.Column("review_task_id", sa.UUID(as_uuid=False), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=False),
        sa.Column("target_role", sa.String(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "in_review", "approved", "rejected",
                "edited_approved", "escalated",
                name="reviewtaskstatusenum",
            ),
            nullable=False,
        ),
        sa.Column(
            "priority",
            sa.Enum("high", "medium", "low", name="reviewtaskpriorityenum"),
            nullable=False,
        ),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("assigned_reviewer_id", sa.String(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("review_task_id"),
        sa.UniqueConstraint("thread_id", name="uq_review_task_thread_id"),
    )
    op.create_index("ix_review_task_status", "review_task", ["status"])
    op.create_index("ix_review_task_sla_due_at", "review_task", ["sla_due_at"])


def downgrade() -> None:
    op.drop_index("ix_review_task_sla_due_at", table_name="review_task")
    op.drop_index("ix_review_task_status", table_name="review_task")
    op.drop_table("review_task")
    sa.Enum(name="reviewtaskpriorityenum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reviewtaskstatusenum").drop(op.get_bind(), checkfirst=True)