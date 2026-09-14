"""
Orchestrates the extract stage of FR-1's pipeline (extract -> clean ->
chunk -> embed -> index). This use case only covers extract+status —
chunking/embedding are separate, later use cases, kept independently
testable per the brief's "separable, testable stages" requirement.

Idempotency: re-ingesting the same file (same content hash) is a no-op
that returns an IngestionResult with was_skipped=True and pages=[],
allowing downstream chunk/embed stages to short-circuit immediately.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from backend.domain.entities.document import (
    Document,
    IngestionStatus,
    IngestionStatusEnum,
)
from backend.domain.errors.ingestion_errors import (
    DocumentExtractionError,
    UnsupportedFileTypeError,
)
from backend.domain.ports.document_repository import DocumentRepository


@dataclass(frozen=True)
class IngestionResult:
    document: Document
    pages: list[dict] = field(default_factory=list)
    was_skipped: bool = False


class IngestDocumentUseCase:
    def __init__(
        self,
        repository: DocumentRepository,
        extractors: dict[str, Callable[[Path], list[dict]]] | None = None,
        hash_fn: Callable[[Path], str] | None = None,
    ):
        self._repository = repository

        # Lazy load infrastructure defaults only when not injected
        if extractors is not None:
            self._extractors = extractors
        else:
            from backend.infrastructure.ingestion.docx_extractor import (
                extract_docx_text,
            )
            from backend.infrastructure.ingestion.pdf_extractor import extract_pdf_text

            self._extractors = {
                ".pdf": extract_pdf_text,
                ".docx": extract_docx_text,
            }

        if hash_fn is not None:
            self._hash_fn = hash_fn
        else:
            from backend.infrastructure.ingestion.pdf_extractor import compute_file_hash

            self._hash_fn = compute_file_hash

    def execute(
        self,
        file_path: Path,
        source: str,
        version: str,
        doc_category: str | None = None,
    ) -> IngestionResult:
        file_hash = self._hash_fn(file_path)

        existing = self._repository.get_by_hash(file_hash)
        if existing is not None:
            # Idempotent re-ingestion: identical content, short-circuit
            return IngestionResult(document=existing, pages=[], was_skipped=True)

        extractor = self._extractors.get(file_path.suffix.lower())
        if extractor is None:
            raise UnsupportedFileTypeError(
                f"No extractor registered for '{file_path.suffix}'"
            )

        now = datetime.now(timezone.utc)
        document = Document(
            doc_id=str(uuid.uuid4()),
            source=source,
            version=version,
            hash=file_hash,
            doc_category=doc_category,
            created_at=now,
            updated_at=now,
        )
        self._repository.save_document(document)
        self._set_status(document.doc_id, IngestionStatusEnum.PROCESSING)

        try:
            pages = extractor(file_path)
        except Exception as exc:
            self._set_status(
                document.doc_id, IngestionStatusEnum.FAILED, error_message=str(exc)
            )
            raise DocumentExtractionError(
                f"Extraction failed for {file_path.name}: {exc}"
            ) from exc

        if not pages:
            self._set_status(
                document.doc_id,
                IngestionStatusEnum.FAILED,
                error_message="Extractor returned no text content",
            )
            raise DocumentExtractionError(f"No extractable text in {file_path.name}")

        # Extracted successfully; status remains PROCESSING until the full pipeline
        # (chunk, embed, index) completes.
        self._set_status(document.doc_id, IngestionStatusEnum.PROCESSING)
        document.updated_at = datetime.now(timezone.utc)
        self._repository.save_document(document)
        return IngestionResult(document=document, pages=pages, was_skipped=False)

    def _set_status(
        self, doc_id: str, status: IngestionStatusEnum, error_message: str | None = None
    ) -> None:
        self._repository.save_ingestion_status(
            IngestionStatus(
                id=str(uuid.uuid4()),
                doc_id=doc_id,
                status=status,
                updated_at=datetime.now(timezone.utc),
                error_message=error_message,
            )
        )
