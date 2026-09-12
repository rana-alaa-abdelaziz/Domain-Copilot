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

    def search(self, query_text: str, top_k: int = 5) -> list[dict]:
        rows = self._session.execute(
            text(
                """
                SELECT chunk_id, doc_id, content, page, standard_id,
                       ts_rank(search_vector, websearch_to_tsquery('english', :query_text)) AS score
                FROM chunk
                WHERE search_vector @@ websearch_to_tsquery('english', :query_text)
                ORDER BY score DESC
                LIMIT :top_k
                """
            ),
            {"query_text": query_text, "top_k": top_k},
        ).mappings().all()
        # Same str-cast as PgVectorStore.query() — raw SQL returns native
        # uuid.UUID objects for these columns; normalize to str to match
        # every other part of the domain layer.
        return [
            {**dict(row), "chunk_id": str(row["chunk_id"]), "doc_id": str(row["doc_id"])}
            for row in rows
        ]
