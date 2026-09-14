"""add search_vector column to chunk for keyword search

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-12 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Generated column: Postgres maintains this automatically on every
    # insert/update of `content` — no application code has to remember to
    # recompute it. 'english' config is a pragmatic default for this
    # corpus; revisit per-document language config if a non-English
    # source is added later (see ADR-001 twist note if bilingual retrieval
    # is ever in scope).
    op.execute(
        """
        ALTER TABLE chunk
        ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunk_search_vector "
        "ON chunk USING GIN (search_vector);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_search_vector;")
    op.execute("ALTER TABLE chunk DROP COLUMN IF EXISTS search_vector;")
