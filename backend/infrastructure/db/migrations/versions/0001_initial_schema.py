"""initial schema document ingestion

Revision ID: 0001
Revises:
Create Date: 2026-09-11 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create document table
    op.create_table(
        "document",
        sa.Column("doc_id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 2. Create ingestion_status table
    op.create_table(
        "ingestion_status",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("document.doc_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "processing",
                "ready",
                "failed",
                name="ingestion_status_enum",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 3. Create chunk table
    op.create_table(
        "chunk",
        sa.Column("chunk_id", postgresql.UUID(as_uuid=False), primary_key=True, nullable=False),
        sa.Column(
            "doc_id",
            postgresql.UUID(as_uuid=False),
            sa.ForeignKey("document.doc_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("standard_id", sa.String(length=128), nullable=True),
        sa.Column("hierarchy_path", sa.String(length=512), nullable=True),
        sa.Column("page", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("doc_id", "chunk_index", name="uq_chunk_doc_order"),
    )


def downgrade() -> None:
    op.drop_table("chunk")
    op.drop_table("ingestion_status")
    op.drop_table("document")

    # Drop enum type
    op.execute("DROP TYPE IF EXISTS ingestion_status_enum;")
