"""
Port the application layer depends on for chunk persistence. Infrastructure
provides the SQLAlchemy-backed implementation. No infra import here — same
boundary DocumentRepository establishes.
"""

from abc import ABC, abstractmethod

from backend.domain.entities.chunk import Chunk


class ChunkRepository(ABC):
    @abstractmethod
    def get_chunks_by_doc(self, doc_id: str) -> list[Chunk]:
        """Used for idempotent re-chunking — if chunks already exist for
        this doc_id, the use case short-circuits rather than re-inserting."""

    @abstractmethod
    def save_chunks(self, chunks: list[Chunk]) -> None:
        """Persist a batch of chunks for a single document."""

    @abstractmethod
    def delete_chunks_by_doc(self, doc_id: str) -> None:
        """Supports a future explicit re-chunk operation (not used by the
        default idempotent path, but needed so re-chunking isn't a one-way
        door once a strategy changes)."""

    @abstractmethod
    def get_unembedded_chunks(self, doc_id: str) -> list[Chunk]:
        """Chunks for this doc that have not yet had an embedding written —
        drives EmbedChunksUseCase's idempotency (skip chunks already done)."""

    @abstractmethod
    def save_embeddings(self, embeddings: dict[str, list[float]]) -> None:
        """embeddings maps chunk_id -> vector. Batched rather than one
        call per chunk to avoid a query-per-chunk cost on large corpora.
        Dense similarity search itself lives on the VectorStore port, not
        here — ChunkRepository owns chunk CRUD, VectorStore owns retrieval,
        so swapping vector stores later never touches this repository."""
