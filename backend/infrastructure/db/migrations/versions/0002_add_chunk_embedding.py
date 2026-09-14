"""add embedding column to chunk

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-12 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 768 dims: matches Ollama's nomic-embed-text natively, and OpenAI's
# text-embedding-3-small is called with dimensions=768 to match — see
# ADR covering provider abstraction. Keeping both adapters on one
# dimension means swapping providers via config never requires a
# schema migration.
EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.add_column(
        "chunk",
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
    )
    # ivfflat index for approximate nearest-neighbor search; lists=100 is a
    # reasonable default for a corpus in the low thousands of chunks, per
    # pgvector's own sizing guidance (roughly sqrt(N) to N/1000 rows).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunk_embedding "
        "ON chunk USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding;")
    op.drop_column("chunk", "embedding")
