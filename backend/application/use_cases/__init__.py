from backend.application.use_cases.chunk_document import (
    ChunkDocumentUseCase,
    ChunkingResult,
)
from backend.application.use_cases.ingest_document import (
    IngestDocumentUseCase,
    IngestionResult,
)
from backend.application.use_cases.ingest_pipeline import (
    IngestPipelineUseCase,
    PipelineResult,
)


class SubmitForReview:
    def publish(self, item, review_task):
        raise NotImplementedError(
            "Publish path not yet implemented — this must enforce the "
            "review-queue approval gate before landing real logic."
        )


__all__ = [
    "ChunkDocumentUseCase",
    "ChunkingResult",
    "IngestDocumentUseCase",
    "IngestPipelineUseCase",
    "IngestionResult",
    "PipelineResult",
    "SubmitForReview",
]
