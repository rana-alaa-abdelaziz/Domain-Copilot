"""
Full corpus ingestion script for Domain-Copilot.

Orchestrates the FR-1 pipeline (extract -> clean -> chunk -> embed -> index)
across all standards documents in `corpus/standards/` against the primary
development database configured in `DATABASE_URL`.
"""
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.application.use_cases.chunk_document import ChunkDocumentUseCase
from backend.application.use_cases.embed_chunks import EmbedChunksUseCase
from backend.application.use_cases.ingest_document import IngestDocumentUseCase
from backend.application.use_cases.ingest_pipeline import IngestPipelineUseCase
from backend.infrastructure.config import get_llm_provider, get_settings
from backend.infrastructure.db.models import Chunk as OrmChunk
from backend.infrastructure.db.models import Document as OrmDocument
from backend.infrastructure.db.repositories.chunk_repository import (
    SqlAlchemyChunkRepository,
)
from backend.infrastructure.db.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)


def main():
    load_dotenv()
    settings = get_settings()

    db_url = settings.database_url
    if not db_url:
        print("ERROR: DATABASE_URL not set in environment or .env file.")
        sys.exit(1)

    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    print(f"Connecting to database: {db_url.split('@')[-1] if '@' in db_url else db_url}")
    engine = create_engine(db_url)
    Session = sessionmaker(bind=engine)
    session = Session()

    doc_repo = SqlAlchemyDocumentRepository(session)
    chunk_repo = SqlAlchemyChunkRepository(session)
    llm_provider = get_llm_provider(settings)

    print(f"Using LLM provider for embeddings: {type(llm_provider).__name__}")

    ingest_uc = IngestDocumentUseCase(repository=doc_repo)
    chunk_uc = ChunkDocumentUseCase(chunk_repository=chunk_repo)
    embed_uc = EmbedChunksUseCase(
        chunk_repository=chunk_repo,
        document_repository=doc_repo,
        llm_provider=llm_provider,
    )
    pipeline = IngestPipelineUseCase(
        ingest_document_use_case=ingest_uc,
        chunk_document_use_case=chunk_uc,
        embed_chunks_use_case=embed_uc,
    )

    corpus_dir = project_root / "corpus" / "standards"
    if not corpus_dir.exists():
        print(f"ERROR: Corpus directory not found at {corpus_dir}")
        sys.exit(1)

    files = sorted(
        [p for p in corpus_dir.iterdir() if p.suffix.lower() in [".pdf", ".docx"]]
    )
    print(f"Found {len(files)} files to process in {corpus_dir}\n")

    total_chunks = 0
    total_embedded = 0

    for idx, file_path in enumerate(files, start=1):
        print(f"[{idx}/{len(files)}] Processing {file_path.name}...")
        try:
            result = pipeline.execute(
                file_path=file_path,
                source=file_path.name,
                version="1.0",
            )
            if result.ingestion.was_skipped:
                print("       -> Ingestion skipped (already ingested, hash match).")
            else:
                chunks_count = len(result.chunking.chunks) if result.chunking else 0
                embedded_count = (
                    result.embedding.embedded_count if result.embedding else 0
                )
                total_chunks += chunks_count
                total_embedded += embedded_count
                print(
                    f"       -> Ingested: {chunks_count} chunks produced, {embedded_count} embedded."
                )
        except Exception as e:  # noqa: BLE001
            print(f"       -> ERROR processing {file_path.name}: {e}")

    session.close()

    # Verify counts directly from DB
    verify_session = Session()
    doc_count = verify_session.scalar(select(func.count(OrmDocument.doc_id)))
    chunk_count = verify_session.scalar(select(func.count(OrmChunk.chunk_id)))
    embedded_chunk_count = verify_session.scalar(
        select(func.count(OrmChunk.chunk_id)).where(OrmChunk.embedding.isnot(None))
    )
    verify_session.close()

    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    print(f"Total documents in database: {doc_count}")
    print(f"Total chunks in database:    {chunk_count}")
    print(f"Total embedded chunks:       {embedded_chunk_count}")
    print("=" * 60)


if __name__ == "__main__":
    main()
