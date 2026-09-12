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

    def upsert(self, ids: list[str], vectors: list[list[float]], metadata: list[dict]) -> None:
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

    def query(self, vector: list[float], top_k: int = 5) -> list[dict]:
        # Cosine distance (<=>) via pgvector; lower distance = more similar,
        # so score is reported as 1 - distance to read as "higher is better"
        # for consistency with how a fusion step will combine this with
        # keyword scores later.
        rows = self._session.execute(
            text(
                """
                SELECT chunk_id, doc_id, content, page, standard_id,
                       1 - (embedding <=> CAST(:query_vector AS vector)) AS score
                FROM chunk
                WHERE embedding IS NOT NULL
                  AND (embedding <=> CAST(:query_vector AS vector)) < 1.0
                ORDER BY embedding <=> CAST(:query_vector AS vector)
                LIMIT :top_k
                """
            ),
            {"query_vector": str(vector), "top_k": top_k},
        ).mappings().all()
        return [
            {**dict(row), "chunk_id": str(row["chunk_id"]), "doc_id": str(row["doc_id"])}
            for row in rows
        ]
