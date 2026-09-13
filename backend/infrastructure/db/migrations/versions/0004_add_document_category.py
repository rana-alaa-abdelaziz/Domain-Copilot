"""add doc_category to document

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-16 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Free-text on purpose, not a DB enum: the metadata-filtering spec names
# three categories (requirement, methodology, reference_curriculum) as
# the ones the Standards Mapper agent actually queries against, but
# nothing else in the domain constrains category to only these three —
# a DB-level enum here would force a migration every time a new category
# is introduced. Validation of allowed values, if wanted, belongs in the
# application layer, not the schema.
CATEGORY_COLUMN = "doc_category"


def upgrade() -> None:
    op.add_column(
        "document",
        sa.Column(CATEGORY_COLUMN, sa.String(), nullable=True),
    )
    op.create_index(
        "ix_document_doc_category", "document", [CATEGORY_COLUMN]
    )


def downgrade() -> None:
    op.drop_index("ix_document_doc_category", table_name="document")
    op.drop_column("document", CATEGORY_COLUMN)
