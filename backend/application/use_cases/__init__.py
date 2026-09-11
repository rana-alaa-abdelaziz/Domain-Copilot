from backend.application.use_cases.ingest_document import (
    IngestDocumentUseCase,
    IngestionResult,
)


class SubmitForReview:
    def publish(self, item, review_task):
        raise NotImplementedError(
            "Publish path not yet implemented — this must enforce the "
            "review-queue approval gate before landing real logic."
        )

__all__ = [
    "IngestDocumentUseCase",
    "IngestionResult",
    "SubmitForReview",
]