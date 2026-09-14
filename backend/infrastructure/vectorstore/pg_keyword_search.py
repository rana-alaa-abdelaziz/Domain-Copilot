"""
KeywordSearchPort implementation backed by Postgres full-text search
(tsvector/tsquery) against the same chunk table PgVectorStore queries —
no separate search engine, per the documented single-database decision.

ts_rank score is reported as-is (unbounded, roughly 0-1 in practice but
not guaranteed) — the fusion step (domain/services/retrieval_fusion.py)
uses rank position, not raw score magnitude, so dense and keyword scores
never need to be on the same scale.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.domain.ports import KeywordSearchPort


class PgKeywordSearch(KeywordSearchPort):
    def __init__(self, session: Session):
        self._session = session

    def search(
        self, query_text: str, top_k: int = 5, doc_category: str | None = None
    ) -> list[dict]:
        category_filter_sql = ""
        params = {"query_text": query_text, "top_k": top_k}
        if doc_category is not None:
            category_filter_sql = "AND document.doc_category = :doc_category"
            params["doc_category"] = doc_category

        rows = (
            self._session.execute(
                text(
                    f"""
                SELECT chunk.chunk_id, chunk.doc_id, chunk.content, chunk.page,
                       chunk.standard_id,
                       ts_rank(chunk.search_vector, websearch_to_tsquery('english', :query_text)) AS score
                FROM chunk
                JOIN document ON document.doc_id = chunk.doc_id
                WHERE chunk.search_vector @@ websearch_to_tsquery('english', :query_text)
                  {category_filter_sql}
                ORDER BY score DESC
                LIMIT :top_k
                """
                ),
                params,
            )
            .mappings()
            .all()
        )
        # Same str-cast as PgVectorStore.query() — raw SQL returns native
        # uuid.UUID objects for these columns; normalize to str to match
        # every other part of the domain layer.
        return [
            {
                **dict(row),
                "chunk_id": str(row["chunk_id"]),
                "doc_id": str(row["doc_id"]),
            }
            for row in rows
        ]
