"""
Port the application layer depends on. Infrastructure provides the
SQLAlchemy-backed implementation. No infra import here — this is the
boundary the acceptance test (swap DB, no business-logic change) checks.
"""

from abc import ABC, abstractmethod

from backend.domain.entities.document import Document, IngestionStatus


class DocumentRepository(ABC):
    @abstractmethod
    def get_by_hash(self, file_hash: str) -> Document | None:
        """Used for idempotent re-ingestion — if a hash already exists,
        the use case short-circuits rather than re-inserting."""

    @abstractmethod
    def get_by_id(self, doc_id: str) -> Document | None:
        """Fetch a document by its primary key (doc_id)."""

    @abstractmethod
    def save_document(self, document: Document) -> None:
        """Persist or update a Document entity."""

    @abstractmethod
    def save_ingestion_status(self, status: IngestionStatus) -> None:
        """Persist or update an IngestionStatus record."""

    @abstractmethod
    def get_ingestion_status(self, doc_id: str) -> IngestionStatus | None:
        """Supports FR-1's per-document status/failure reporting."""
