from pathlib import Path

import fitz
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.application.use_cases.chunk_document import ChunkDocumentUseCase
from backend.application.use_cases.embed_chunks import EmbedChunksUseCase
from backend.application.use_cases.ingest_document import IngestDocumentUseCase
from backend.application.use_cases.ingest_pipeline import IngestPipelineUseCase
from backend.domain.entities.document import IngestionStatusEnum
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
from backend.infrastructure.db.repositories.chunk_repository import (
    SqlAlchemyChunkRepository,
)
from backend.infrastructure.db.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from backend.infrastructure.llm.stub_adapter import StubLlmAdapter
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


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "sample_standards.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "STD-101.1 Basic Arithmetic and Algebra\n"
        "Students will understand standard operations, variables, and equations.",
    )
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_pipeline_extracts_and_chunks_new_document(db_session, sample_pdf: Path):
    doc_repo = SqlAlchemyDocumentRepository(db_session)
    chunk_repo = SqlAlchemyChunkRepository(db_session)

    ingest_uc = IngestDocumentUseCase(repository=doc_repo)
    chunk_uc = ChunkDocumentUseCase(chunk_repository=chunk_repo)

    # Isolated check first, before the full pipeline runs: chunking alone
    # must never prematurely mark the document READY. This replaces the
    # old post-pipeline assertion of the same intent — that assertion is
    # no longer true post-pipeline now that embedding (which legitimately
    # sets READY) runs as part of the same execute() call below.
    pre_embed_ingestion = ingest_uc.execute(
        sample_pdf, source="sample_standards.pdf", version="1.0"
    )
    pre_embed_chunking = chunk_uc.execute(
        pre_embed_ingestion.document.doc_id, pre_embed_ingestion.pages
    )
    status_after_chunk_only = doc_repo.get_ingestion_status(
        pre_embed_ingestion.document.doc_id
    )
    assert status_after_chunk_only.status == IngestionStatusEnum.PROCESSING
    assert status_after_chunk_only.status != IngestionStatusEnum.READY
    assert len(pre_embed_chunking.chunks) > 0

    # Now run the full pipeline (ingest+chunk+embed) fresh, against a
    # second file, so this test's main assertions aren't relying on the
    # partially-processed state from the isolated check above.
    embed_uc = EmbedChunksUseCase(
        chunk_repository=chunk_repo,
        document_repository=doc_repo,
        llm_provider=StubLlmAdapter(),
    )
    pipeline = IngestPipelineUseCase(
        ingest_document_use_case=ingest_uc,
        chunk_document_use_case=chunk_uc,
        embed_chunks_use_case=embed_uc,
    )

    second_pdf = sample_pdf.parent / "sample_standards_2.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (50, 72),
        "STD-101.1 Basic Arithmetic and Algebra\n"
        "Students will understand standard operations, variables, and equations.",
    )
    doc.save(str(second_pdf))
    doc.close()

    result = pipeline.execute(second_pdf, source="sample_standards_2.pdf", version="1.0")

    # 1. Assert ingestion succeeded and was not skipped
    assert result.ingestion.was_skipped is False
    assert result.ingestion.document is not None

    # 2. Assert chunking occurred and chunks were produced
    assert result.chunking is not None
    assert len(result.chunking.chunks) > 0
    assert result.chunking.was_skipped is False

    # 3. Assert embedding ran and the document is now READY — this is the
    # correct end state for a full, successful pipeline run.
    assert result.embedding is not None
    assert result.embedding.embedded_count == len(result.chunking.chunks)
    assert result.embedding.was_skipped is False

    persisted_status = doc_repo.get_ingestion_status(result.ingestion.document.doc_id)
    assert persisted_status is not None
    assert persisted_status.status == IngestionStatusEnum.READY

    # 4. Assert chunk rows exist in real Postgres database, with embeddings written
    persisted_chunks = chunk_repo.get_chunks_by_doc(result.ingestion.document.doc_id)
    assert len(persisted_chunks) == len(result.chunking.chunks)
    assert persisted_chunks[0].standard_id == "STD-101.1"
    assert persisted_chunks[0].embedding is not None
    assert len(persisted_chunks[0].embedding) == 768


def test_pipeline_skips_chunking_on_idempotent_reingestion(
    db_session, sample_pdf: Path
):
    doc_repo = SqlAlchemyDocumentRepository(db_session)
    chunk_repo = SqlAlchemyChunkRepository(db_session)

    ingest_uc = IngestDocumentUseCase(repository=doc_repo)
    chunk_uc = ChunkDocumentUseCase(chunk_repository=chunk_repo)
    embed_uc = EmbedChunksUseCase(
        chunk_repository=chunk_repo,
        document_repository=doc_repo,
        llm_provider=StubLlmAdapter(),
    )
    pipeline = IngestPipelineUseCase(
        ingest_document_use_case=ingest_uc,
        chunk_document_use_case=chunk_uc,
        embed_chunks_use_case=embed_uc,
    )

    # First run: extracts and chunks
    first_result = pipeline.execute(
        sample_pdf, source="sample_standards.pdf", version="1.0"
    )
    assert first_result.ingestion.was_skipped is False
    assert first_result.chunking is not None
    doc_id = first_result.ingestion.document.doc_id

    initial_chunks = chunk_repo.get_chunks_by_doc(doc_id)
    initial_chunk_count = len(initial_chunks)
    assert initial_chunk_count > 0

    # Second run: identical file content, must skip ingestion and chunking
    second_result = pipeline.execute(
        sample_pdf, source="sample_standards.pdf", version="1.0"
    )
    assert second_result.ingestion.was_skipped is True
    assert second_result.chunking is None
    assert second_result.embedding is None

    # Assert no duplicate chunk rows were created in Postgres
    chunks_after_reingest = chunk_repo.get_chunks_by_doc(doc_id)
    assert len(chunks_after_reingest) == initial_chunk_count
