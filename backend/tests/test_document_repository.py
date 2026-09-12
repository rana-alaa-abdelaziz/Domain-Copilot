import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.domain.entities.document import (
    Document as DomainDocument,
)
from backend.domain.entities.document import (
    IngestionStatus as DomainIngestionStatus,
)
from backend.domain.entities.document import (
    IngestionStatusEnum as DomainIngestionStatusEnum,
)
from backend.infrastructure.db.models import (
    Base,
)
from backend.infrastructure.db.models import (
    Chunk as OrmChunk,
)
from backend.infrastructure.db.models import (
    Document as OrmDocument,
)
from backend.infrastructure.db.models import (
    IngestionStatus as OrmIngestionStatus,
)
from backend.infrastructure.db.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from backend.tests.db_test_utils import ensure_test_db_exists, get_test_db_url

DB_URL = get_test_db_url()


@pytest.fixture
def db_session():
    ensure_test_db_exists(DB_URL)
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.query(OrmChunk).delete()
    session.query(OrmIngestionStatus).delete()
    session.query(OrmDocument).delete()
    session.commit()
    yield session
    session.close()



def test_save_and_get_document_by_hash(db_session):
    repo = SqlAlchemyDocumentRepository(db_session)
    now = datetime.now(timezone.utc)
    doc_id = str(uuid.uuid4())
    doc = DomainDocument(
        doc_id=doc_id,
        source="syllabus.pdf",
        version="v1.0",
        hash="sha256-abc-123",
        created_at=now,
        updated_at=now,
    )

    repo.save_document(doc)

    fetched = repo.get_by_hash("sha256-abc-123")
    assert fetched is not None
    assert fetched.doc_id == doc_id
    assert fetched.source == "syllabus.pdf"
    assert fetched.version == "v1.0"
    assert fetched.hash == "sha256-abc-123"

    by_id = repo.get_by_id(doc_id)
    assert by_id is not None
    assert by_id.doc_id == doc_id

    non_existent = repo.get_by_hash("non-existent-hash")
    assert non_existent is None


def test_update_existing_document(db_session):
    repo = SqlAlchemyDocumentRepository(db_session)
    now = datetime.now(timezone.utc)
    doc_id = str(uuid.uuid4())
    doc = DomainDocument(
        doc_id=doc_id,
        source="syllabus.pdf",
        version="v1.0",
        hash="sha256-def-456",
        created_at=now,
        updated_at=now,
    )
    repo.save_document(doc)

    later = datetime.now(timezone.utc)
    doc_updated = DomainDocument(
        doc_id=doc_id,
        source="syllabus_updated.pdf",
        version="v2.0",
        hash="sha256-def-456-new",
        created_at=now,
        updated_at=later,
    )
    repo.save_document(doc_updated)

    fetched = repo.get_by_id(doc_id)
    assert fetched is not None
    assert fetched.source == "syllabus_updated.pdf"
    assert fetched.version == "v2.0"
    assert fetched.hash == "sha256-def-456-new"


def test_save_and_get_ingestion_status(db_session):
    repo = SqlAlchemyDocumentRepository(db_session)
    now = datetime.now(timezone.utc)
    doc_id = str(uuid.uuid4())
    doc = DomainDocument(
        doc_id=doc_id,
        source="test.docx",
        version="v1.0",
        hash="sha256-status-test",
        created_at=now,
        updated_at=now,
    )
    repo.save_document(doc)

    status_id = str(uuid.uuid4())
    status = DomainIngestionStatus(
        id=status_id,
        doc_id=doc_id,
        status=DomainIngestionStatusEnum.PROCESSING,
        updated_at=now,
        error_message=None,
    )
    repo.save_ingestion_status(status)

    fetched_status = repo.get_ingestion_status(doc_id)
    assert fetched_status is not None
    assert fetched_status.id == status_id
    assert fetched_status.doc_id == doc_id
    assert fetched_status.status == DomainIngestionStatusEnum.PROCESSING
    assert fetched_status.error_message is None

    # Update status to READY
    later = datetime.now(timezone.utc)
    ready_status = DomainIngestionStatus(
        id=status_id,
        doc_id=doc_id,
        status=DomainIngestionStatusEnum.READY,
        updated_at=later,
        error_message=None,
    )
    repo.save_ingestion_status(ready_status)

    updated_fetch = repo.get_ingestion_status(doc_id)
    assert updated_fetch is not None
    assert updated_fetch.status == DomainIngestionStatusEnum.READY


def test_get_ingestion_status_not_found(db_session):
    repo = SqlAlchemyDocumentRepository(db_session)
    assert repo.get_ingestion_status(str(uuid.uuid4())) is None


def test_ingest_use_case_with_sqlalchemy_repository(db_session, tmp_path):
    from backend.application.use_cases.ingest_document import IngestDocumentUseCase

    repo = SqlAlchemyDocumentRepository(db_session)
    dummy_pdf = tmp_path / "math_standards.pdf"
    dummy_pdf.write_bytes(b"%PDF-dummy")

    fake_pages = [{"page": 1, "text": "Grade 5 Math Standards"}]
    use_case = IngestDocumentUseCase(
        repository=repo,
        extractors={".pdf": lambda p: fake_pages},
        hash_fn=lambda p: "hash-real-db-test",
    )

    # 1. Fresh execution
    result = use_case.execute(dummy_pdf, source="math_standards.pdf", version="1.0")
    assert not result.was_skipped
    assert result.pages == fake_pages

    # Check persistence
    stored_doc = repo.get_by_hash("hash-real-db-test")
    assert stored_doc is not None
    assert stored_doc.source == "math_standards.pdf"
    stored_status = repo.get_ingestion_status(stored_doc.doc_id)
    assert stored_status is not None
    assert stored_status.status == DomainIngestionStatusEnum.PROCESSING

    # 2. Idempotent re-ingestion
    reingest_result = use_case.execute(dummy_pdf, source="math_standards.pdf", version="1.0")
    assert reingest_result.was_skipped is True
    assert reingest_result.pages == []
    assert reingest_result.document.doc_id == stored_doc.doc_id

