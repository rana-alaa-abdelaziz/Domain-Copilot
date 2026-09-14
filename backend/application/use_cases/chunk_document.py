"""
Orchestrates the chunk stage of FR-1's pipeline (extract -> clean ->
chunk -> embed -> index). Takes the sections produced by
IngestDocumentUseCase.execute() and turns them into persisted Chunk rows.

Idempotency: if chunks already exist for a doc_id, this is a no-op —
mirrors IngestDocumentUseCase's hash-based skip, but keyed on doc_id since
chunking is a downstream stage of an already-deduplicated document.

Status note: this stage does NOT set IngestionStatus to READY. READY is
reserved for the final embed+index stage — a chunked-but-not-yet-embedded
document must still read as PROCESSING, or nothing downstream has an
accurate signal that it still needs work.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from backend.domain.entities.chunk import Chunk
from backend.domain.errors.ingestion_errors import ChunkingError
from backend.domain.ports.chunk_repository import ChunkRepository
from backend.domain.services.chunking import chunk_sections


@dataclass(frozen=True)
class ChunkingResult:
    doc_id: str
    chunks: list[Chunk] = field(default_factory=list)
    was_skipped: bool = False


class ChunkDocumentUseCase:
    def __init__(
        self,
        chunk_repository: ChunkRepository,
        chunker: Callable[[str, list[dict]], list[Chunk]] | None = None,
    ):
        self._chunk_repository = chunk_repository
        self._chunker = chunker if chunker is not None else chunk_sections

    def execute(self, doc_id: str, sections: list[dict]) -> ChunkingResult:
        existing = self._chunk_repository.get_chunks_by_doc(doc_id)
        if existing:
            return ChunkingResult(doc_id=doc_id, chunks=existing, was_skipped=True)

        chunks = self._chunker(doc_id, sections)
        if not chunks:
            raise ChunkingError(
                f"Chunking produced zero chunks for doc_id={doc_id} "
                f"despite {len(sections)} extracted section(s)"
            )

        self._chunk_repository.save_chunks(chunks)
        return ChunkingResult(doc_id=doc_id, chunks=chunks, was_skipped=False)
