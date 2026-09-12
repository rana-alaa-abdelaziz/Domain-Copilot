"""
Orchestrates the embed stage of FR-1's pipeline (extract -> clean ->
chunk -> embed -> index). Takes chunks already persisted by
ChunkDocumentUseCase and writes an embedding vector for each.

Idempotency: only chunks with no embedding yet are sent to the provider —
re-running this use case against an already-fully-embedded document is a
no-op, mirroring the hash/doc_id-based skip pattern used by the two
earlier pipeline stages.

Status transition: this is the stage that finally sets IngestionStatus to
READY, per the note in chunk_document.py — a document only reads as fully
usable once its chunks are both persisted AND embedded, not merely
persisted.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from backend.domain.entities.chunk import Chunk
from backend.domain.entities.document import IngestionStatus, IngestionStatusEnum
from backend.domain.errors.ingestion_errors import EmbeddingError
from backend.domain.ports import LlmProvider
from backend.domain.ports.chunk_repository import ChunkRepository
from backend.domain.ports.document_repository import DocumentRepository


@dataclass(frozen=True)
class EmbeddingResult:
    doc_id: str
    embedded_count: int
    was_skipped: bool = False


class EmbedChunksUseCase:
    def __init__(
        self,
        chunk_repository: ChunkRepository,
        document_repository: DocumentRepository,
        llm_provider: LlmProvider,
    ):
        self._chunk_repository = chunk_repository
        self._document_repository = document_repository
        self._llm_provider = llm_provider

    def execute(self, doc_id: str) -> EmbeddingResult:
        unembedded = self._chunk_repository.get_unembedded_chunks(doc_id)

        if not unembedded:
            # Either already fully embedded (idempotent skip) or chunking
            # hasn't produced anything yet — both cases mean "nothing to
            # do here", so treat uniformly rather than distinguishing,
            # since ChunkDocumentUseCase already raises if chunking itself
            # produced zero chunks.
            return EmbeddingResult(doc_id=doc_id, embedded_count=0, was_skipped=True)

        embeddings: dict[str, list[float]] = {}
        for chunk in unembedded:
            embeddings[chunk.chunk_id] = self._embed_one(chunk)

        self._chunk_repository.save_embeddings(embeddings)
        self._mark_ready(doc_id)

        return EmbeddingResult(
            doc_id=doc_id, embedded_count=len(embeddings), was_skipped=False
        )

    def _embed_one(self, chunk: Chunk) -> list[float]:
        try:
            return self._llm_provider.embed(chunk.content)
        except Exception as exc:
            self._mark_failed(chunk.doc_id, str(exc))
            raise EmbeddingError(
                f"Embedding failed for chunk_id={chunk.chunk_id} "
                f"doc_id={chunk.doc_id}: {exc}"
            ) from exc

    def _mark_ready(self, doc_id: str) -> None:
        self._document_repository.save_ingestion_status(
            IngestionStatus(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                status=IngestionStatusEnum.READY,
                updated_at=datetime.now(timezone.utc),
            )
        )

    def _mark_failed(self, doc_id: str, error_message: str) -> None:
        self._document_repository.save_ingestion_status(
            IngestionStatus(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                status=IngestionStatusEnum.FAILED,
                updated_at=datetime.now(timezone.utc),
                error_message=error_message,
            )
        )
