"""
VectorStore implementation backed by the same Postgres instance via
pgvector, querying the chunk table's embedding column directly rather
than a separate vector-only store — the deliberate single-database
choice documented in the vector-store-choice ADR.

Kept separate from ChunkRepository even though both touch the chunk
table: ChunkRepository owns chunk CRUD, this owns similarity search.
Swapping to a dedicated vector store (Qdrant, etc.) later means
replacing only this file — ChunkRepository is untouched.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.domain.ports import VectorStore


class PgVectorStore(VectorStore):
    def __init__(self, session: Session):
        self._session = session

    def upsert(
        self, ids: list[str], vectors: list[list[float]], metadata: list[dict]
    ) -> None:
        # metadata is accepted for VectorStore-interface compatibility but
        # unused here: chunk metadata (content, page, standard_id, ...)
        # already lives on the chunk row itself, written by ChunkRepository
        # at chunking time — this store only ever writes the embedding
        # column for an existing chunk_id, never a new row.
        if not ids:
            return
        self._session.execute(
            text("UPDATE chunk SET embedding = :embedding WHERE chunk_id = :chunk_id"),
            [
                {"chunk_id": chunk_id, "embedding": str(vector)}
                for chunk_id, vector in zip(ids, vectors, strict=True)
            ],
        )
        self._session.commit()

    def query(
        self, vector: list[float], top_k: int = 5, doc_category: str | None = None
    ) -> list[dict]:
        # Cosine distance (<=>) via pgvector; lower distance = more similar,
        # so score is reported as 1 - distance to read as "higher is better"
        # for consistency with how a fusion step will combine this with
        # keyword scores later.
        #
        # MIN_SIMILARITY floor: cosine similarity search has no native
        # concept of "no match" — ORDER BY ... LIMIT k always returns k
        # rows, even for a totally out-of-corpus query, because it ranks
        # by relative closeness, not absolute relevance. The previous
        # `distance < 1.0` filter here was effectively a no-op (cosine
        # distance is almost always under 1.0 regardless of actual
        # relevance), which is exactly why the first real eval run
        # (scripts/eval.py) showed 0% refusal correctness: unrelated
        # queries still got back their "5 least-dissimilar" chunks, one
        # of which landed at dense-rank #1 and picked up a real RRF
        # fusion score. 0.3 is a starting value based on that run's
        # observed scores — genuinely unrelated queries scored well below
        # this, real matches well above — recalibrate from real numbers
        # as the corpus grows, per FR-3's "record real numbers" guidance.
        MIN_SIMILARITY = 0.3

        category_filter_sql = ""
        params = {
            "query_vector": str(vector),
            "top_k": top_k,
            "min_similarity": MIN_SIMILARITY,
        }
        if doc_category is not None:
            category_filter_sql = "AND document.doc_category = :doc_category"
            params["doc_category"] = doc_category

        rows = (
            self._session.execute(
                text(
                    f"""
                SELECT chunk.chunk_id, chunk.doc_id, chunk.content, chunk.page,
                       chunk.standard_id, document.source,
                       1 - (chunk.embedding <=> CAST(:query_vector AS vector)) AS score
                FROM chunk
                JOIN document ON document.doc_id = chunk.doc_id
                WHERE chunk.embedding IS NOT NULL
                  AND 1 - (chunk.embedding <=> CAST(:query_vector AS vector)) >= :min_similarity
                  {category_filter_sql}
                ORDER BY chunk.embedding <=> CAST(:query_vector AS vector)
                LIMIT :top_k
                """
                ),
                params,
            )
            .mappings()
            .all()
        )
        return [
            {
                **dict(row),
                "chunk_id": str(row["chunk_id"]),
                "doc_id": str(row["doc_id"]),
            }
            for row in rows
        ]
