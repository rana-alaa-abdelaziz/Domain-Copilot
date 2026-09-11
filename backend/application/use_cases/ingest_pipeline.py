"""
Pipeline composition use case orchestrating IngestDocumentUseCase and
ChunkDocumentUseCase in sequence.

Does not construct repositories directly; dependencies are injected.
Idempotency: if ingestion is skipped (same content hash already exists),
chunking is skipped as well.
"""
from dataclasses import dataclass
from pathlib import Path

from backend.application.use_cases.chunk_document import (
    ChunkDocumentUseCase,
    ChunkingResult,
)
from backend.application.use_cases.ingest_document import (
    IngestDocumentUseCase,
    IngestionResult,
)


@dataclass(frozen=True)
class PipelineResult:
    ingestion: IngestionResult
    chunking: ChunkingResult | None  # None only when ingestion was skipped


class IngestPipelineUseCase:
    def __init__(
        self,
        ingest_document_use_case: IngestDocumentUseCase,
        chunk_document_use_case: ChunkDocumentUseCase,
    ):
        self._ingest = ingest_document_use_case
        self._chunk = chunk_document_use_case

    def execute(self, file_path: Path, source: str, version: str) -> PipelineResult:
        ingestion_result = self._ingest.execute(file_path, source, version)

        if ingestion_result.was_skipped:
            return PipelineResult(ingestion=ingestion_result, chunking=None)

        chunking_result = self._chunk.execute(
            ingestion_result.document.doc_id, ingestion_result.pages
        )
        return PipelineResult(ingestion=ingestion_result, chunking=chunking_result)
