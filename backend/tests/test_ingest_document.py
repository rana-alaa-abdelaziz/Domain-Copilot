from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.application.use_cases.ingest_document import (
    IngestDocumentUseCase,
    IngestionResult,
)
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


class FakeDocumentRepository(DocumentRepository):
    def __init__(self):
        self.documents: dict[str, Document] = {}  # doc_id -> Document
        self.statuses: dict[str, IngestionStatus] = {}  # doc_id -> IngestionStatus

    def get_by_hash(self, file_hash: str) -> Document | None:
        for doc in self.documents.values():
            if doc.hash == file_hash:
                return doc
        return None

    def get_by_id(self, doc_id: str) -> Document | None:
        return self.documents.get(doc_id)

    def save_document(self, document: Document) -> None:
        self.documents[document.doc_id] = document

    def save_ingestion_status(self, status: IngestionStatus) -> None:
        self.statuses[status.doc_id] = status

    def get_ingestion_status(self, doc_id: str) -> IngestionStatus | None:
        return self.statuses.get(doc_id)


def test_fresh_ingestion_success(tmp_path: Path):
    fake_repo = FakeDocumentRepository()
    dummy_file = tmp_path / "test.pdf"
    dummy_file.write_bytes(b"dummy pdf content")

    fake_pages = [{"page": 1, "text": "Extracted text content"}]
    use_case = IngestDocumentUseCase(
        repository=fake_repo,
        extractors={".pdf": lambda p: fake_pages},
        hash_fn=lambda p: "hash-12345",
    )

    result = use_case.execute(dummy_file, source="test.pdf", version="1.0")

    assert isinstance(result, IngestionResult)
    assert not result.was_skipped
    assert result.pages == fake_pages
    assert result.document.hash == "hash-12345"
    assert result.document.source == "test.pdf"
    assert result.document.version == "1.0"

    saved_status = fake_repo.get_ingestion_status(result.document.doc_id)
    assert saved_status is not None
    assert saved_status.status == IngestionStatusEnum.PROCESSING
    assert saved_status.error_message is None


def test_idempotent_reingestion_skips_extraction(tmp_path: Path):
    fake_repo = FakeDocumentRepository()
    now = datetime.now(timezone.utc)
    existing_doc = Document(
        doc_id="doc-existing-id",
        source="already_ingested.pdf",
        version="1.0",
        hash="existing-hash-abc",
        created_at=now,
        updated_at=now,
    )
    fake_repo.save_document(existing_doc)

    extractor_called = False

    def mock_extractor(p):
        nonlocal extractor_called
        extractor_called = True
        return [{"page": 1, "text": "content"}]

    dummy_file = tmp_path / "already_ingested.pdf"
    dummy_file.write_bytes(b"content")

    use_case = IngestDocumentUseCase(
        repository=fake_repo,
        extractors={".pdf": mock_extractor},
        hash_fn=lambda p: "existing-hash-abc",
    )

    result = use_case.execute(dummy_file, source="already_ingested.pdf", version="1.0")

    assert result.was_skipped is True
    assert result.document == existing_doc
    assert result.pages == []
    assert not extractor_called


def test_unsupported_file_type_raises_error(tmp_path: Path):
    fake_repo = FakeDocumentRepository()
    dummy_file = tmp_path / "document.xyz"
    dummy_file.write_bytes(b"dummy")

    use_case = IngestDocumentUseCase(
        repository=fake_repo,
        extractors={".pdf": lambda p: []},
        hash_fn=lambda p: "hash-xyz",
    )

    with pytest.raises(UnsupportedFileTypeError) as exc_info:
        use_case.execute(dummy_file, source="document.xyz", version="1.0")

    assert "No extractor registered for '.xyz'" in str(exc_info.value)


def test_extractor_failure_records_failed_status_and_raises(tmp_path: Path):
    fake_repo = FakeDocumentRepository()
    dummy_file = tmp_path / "corrupt.pdf"
    dummy_file.write_bytes(b"corrupt")

    def broken_extractor(p):
        raise ValueError("Corrupt file header")

    use_case = IngestDocumentUseCase(
        repository=fake_repo,
        extractors={".pdf": broken_extractor},
        hash_fn=lambda p: "hash-corrupt",
    )

    with pytest.raises(DocumentExtractionError) as exc_info:
        use_case.execute(dummy_file, source="corrupt.pdf", version="1.0")

    assert "Extraction failed for corrupt.pdf: Corrupt file header" in str(
        exc_info.value
    )

    doc = fake_repo.get_by_hash("hash-corrupt")
    assert doc is not None
    status = fake_repo.get_ingestion_status(doc.doc_id)
    assert status is not None
    assert status.status == IngestionStatusEnum.FAILED
    assert "Corrupt file header" in (status.error_message or "")


def test_empty_pages_records_failed_status_and_raises(tmp_path: Path):
    fake_repo = FakeDocumentRepository()
    dummy_file = tmp_path / "empty.pdf"
    dummy_file.write_bytes(b"empty")

    use_case = IngestDocumentUseCase(
        repository=fake_repo,
        extractors={".pdf": lambda p: []},
        hash_fn=lambda p: "hash-empty",
    )

    with pytest.raises(DocumentExtractionError) as exc_info:
        use_case.execute(dummy_file, source="empty.pdf", version="1.0")

    assert "No extractable text in empty.pdf" in str(exc_info.value)

    doc = fake_repo.get_by_hash("hash-empty")
    assert doc is not None
    status = fake_repo.get_ingestion_status(doc.doc_id)
    assert status is not None
    assert status.status == IngestionStatusEnum.FAILED
    assert "Extractor returned no text content" in (status.error_message or "")
