# AI Usage Log

## 2026-09-10
An earlier planning session with an AI assistant suggested a workflow
that would have pushed the initial Docker/architecture scaffolding
directly to `main` rather than through branches and PRs. This was caught
and corrected before any code was written: all work since has gone
through feature branches, PRs (#23, #4), self-review comments, and CI
checks before merging. Logged here as the first entry precisely because
it's the kind of correction this log exists to surface — an AI
suggestion that had to be overridden, not just AI output that was
accepted.

## 2026-09-11
- **Ingestion Return Contract Decision**: An AI draft for `IngestDocumentUseCase`
  returned a tuple `(document, pages)` on initial ingestion but a bare `Document`
  on idempotent skip. Rather than re-extracting pages on skip or forcing union
  types (`tuple | Document`), resolved this by creating a dedicated, typed
  `IngestionResult` dataclass (`document`, `pages`, `was_skipped=bool`). Re-extracting
  pages on skip was rejected because raw pages are transient (no `pages` DB table
  in `models.py`) and downstream chunking/embedding stages must short-circuit on
  previously ingested documents to avoid unique constraint violations and duplicate
  vector upserts.
- **Architecture Boundary Enforcement**: Relocated `ingest_document.py` from a
  misplaced `backend/use_cases/` folder into `backend/application/use_cases/` to
  comply with Clean Architecture boundaries (ADR-000) and `test_architecture_boundaries.py`.
- **Infrastructure Implementation**: Implemented `SqlAlchemyDocumentRepository` in
  `backend/infrastructure/db/repositories/document_repository.py` satisfying the domain port
  `backend/domain/ports/document_repository.py`. Resolved enum case sensitivity
  (`IngestionStatusEnum`) so domain entities align with the underlying PostgreSQL enum schema.
- **Premature READY Status Correction**: Fixed `IngestDocumentUseCase` setting `IngestionStatusEnum.READY`
  prematurely after extraction; changed status to `PROCESSING` because full ingestion completion
  is reserved for the final embedding/indexing phase.
- **Pipeline Composition**: Implemented `IngestPipelineUseCase` in `backend/application/use_cases/ingest_pipeline.py`
  composing `IngestDocumentUseCase` and `ChunkDocumentUseCase`, ensuring chunking is bypassed on idempotent
  re-ingestion. Verified against live PostgreSQL container with `test_ingest_pipeline.py`.

## 2026-09-12
- **CI Service Container Port Resolution**: On GitHub Actions runner hosts, service container
  ports map to dynamic host ports rather than binding directly to `localhost:5432`. Replaced
  hardcoded `5432` in CI `DATABASE_URL` with `${{ job.services.postgres.ports[5432] }}` to fix
  `psycopg2.OperationalError: Connection refused`. Maintained strict zero-secret compliance
  (using only runner test container dummy parameters).
- **Architecture Boundary Test Discovery in CI**: In CI, `working-directory: backend` caused
  `Path("backend/domain")` to look for `backend/backend/domain`, finding 0 files and silently
  skipping boundary validation. Anchored `RESTRICTED_ROOTS` to `Path(__file__).resolve().parents[1]`
  so all 15 domain/application files are strictly validated regardless of invocation directory.
- **PDF Extractor Cross-Page Header/Footer Stripping**: Refactored `extract_pdf_text` in `backend/infrastructure/ingestion/pdf_extractor.py` to identify and strip recurring headers/footers across document pages. Replaced single-page `_clean_text` with document-wide frequency analysis (`_find_repeated_lines`) thresholded at 50% page repetition (minimum 2 occurrences), preventing recurring header/footer text from polluting downstream chunks and falsely triggering standard ID extraction.
- **Extended Standard ID Detection**: Extended `_STANDARD_ID_PATTERN` in `backend/domain/services/chunking.py` to support slash-separated identifiers (e.g., `SSC/N0506`, `ISO/IEC27001`, `MEP/Q2601`) in addition to hyphen/dot formats. Added dedicated unit test coverage in `tests/test_pdf_extractor.py` and `tests/test_chunking.py`.
- **Embedding Stage Integration and Domain Entity Fix**:
  - Diagnosed and fixed `Unexpected keyword argument 'embedding' in function backend.domain.entities.chunk.Chunk.__init__`: added `embedding: list[float] | None = None` to the domain entity `Chunk` dataclass so `SqlAlchemyChunkRepository._to_domain` does not fail when hydrating ORM models.
  - Added `get_unembedded_chunks` and `save_embeddings` to `ChunkRepository` port and implemented them in `SqlAlchemyChunkRepository`, deserializing pgvector/NumPy arrays to pure Python `list[float]` at the repository boundary to preserve domain layer isolation.
  - Relocated migration script `0002_add_chunk_embedding.py` into `backend/infrastructure/db/migrations/versions/` so Alembic automatically discovers and applies it (`alembic upgrade head`).
  - Restored `backend/infrastructure/vectorstore` directory structure and added `PgVectorStore`.
  - Enforced 768-dimension consistency across all vector representations: `OpenAIAdapter` (`text-embedding-3-small` with `dimensions=768`), `OllamaAdapter` (`nomic-embed-text`), `StubLlmAdapter` (`[0.0] * 768`), `models.py` (`Vector(768)`), and `Settings.embedding_dim`.
  - Composed `EmbedChunksUseCase` into `IngestPipelineUseCase`, transitioning documents to `IngestionStatusEnum.READY` only upon successful embedding persistence.
  - Updated dependencies in `backend/requirements.in` (`openai`, `ollama`), compiled `backend/requirements.txt` via `pip-compile`, and validated with `pip-audit` (0 known vulnerabilities). All 50 tests passing (45 passed, 5 expected xfailed approval gates) and ruff lint clean.
- **CI pgvector Extension Initialization on Fresh Test Databases**:
  - In CI runner containers where tests run against fresh empty PostgreSQL databases without running Alembic migrations first, `Base.metadata.create_all(engine)` in `test_document_repository.py` failed with `psycopg2.errors.UndefinedObject: type "vector" does not exist`.
  - Added a SQLAlchemy `before_create` DDL listener on `Base.metadata` in `backend/infrastructure/db/models.py` (`DDL("CREATE EXTENSION IF NOT EXISTS vector;").execute_if(dialect="postgresql")`) so any call to `create_all` automatically activates the vector extension on PostgreSQL.
  - Also explicitly added extension initialization to the `db_session` fixture in `backend/tests/test_document_repository.py`.
- **Test Database Isolation & Corpus-Wipe Bug Resolution**:
  - Identified the root cause of the corpus-wipe bug: test fixtures in `backend/tests/test_document_repository.py` and `backend/tests/test_ingest_pipeline.py` ran teardown deletes against `DATABASE_URL` (the active dev database `domain_copilot`), destroying all ingested documents and chunks whenever pytest was executed.
  - Resolved this strictly at the database boundary rather than narrowing fixture DELETE clauses: introduced `TEST_DATABASE_URL` pointing to an isolated test database `domain_copilot_test` in `.env` and `.env.example`.
  - Updated repository and pipeline test fixtures to source `TEST_DATABASE_URL`, guaranteeing that automated tests never touch development or production data.
- **FR-2 Hybrid Retrieval Implementation & Verification**:
  - Created `backend/domain/entities/citation.py` (`Citation` dataclass with `chunk_id`, `doc_id`, `content`, `page`, `standard_id`, `fused_score`, `dense_rank`, `keyword_rank`).
  - Created `backend/domain/ports/keyword_search.py` (`KeywordSearchPort`) and exported it in `backend/domain/ports/__init__.py`.
  - Implemented Reciprocal Rank Fusion (RRF) in `backend/domain/services/retrieval_fusion.py` using deterministic Python arithmetic (`RRF_K = 60`), strictly preserving domain boundary rules.
  - Implemented `backend/application/use_cases/hybrid_retrieve.py` (`HybridRetrieveUseCase`) orchestrating dense vector query and PostgreSQL keyword search with over-fetching (`DEFAULT_OVER_FETCH_MULTIPLIER = 4`) and RRF fusion. Disentangled an accidental swap where test logic had been placed in the use case file.
  - Implemented `backend/infrastructure/vectorstore/pg_keyword_search.py` (`PgKeywordSearch`) querying `search_vector @@ websearch_to_tsquery('english', :query_text)` and normalizing UUID keys to strings.
  - Corrected `PgVectorStore.query` in `backend/infrastructure/vectorstore/pgvector_store.py`: added `str` UUID casting and refined the distance filter `(embedding <=> CAST(:query_vector AS vector)) < 1.0` to filter out orthogonal, negative, and NaN distances cleanly.
  - Created Alembic migration `0003_add_chunk_tsvector.py` adding `search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED` and a GIN index `ix_chunk_search_vector`. Tested reversible schema migration via `alembic downgrade -1` and `alembic upgrade head`.
  - Created unit tests `backend/tests/test_retrieval_fusion.py` (5 tests) and integration tests `backend/tests/test_hybrid_retrieve.py` (3 tests targeting `TEST_DATABASE_URL`).
- **Corpus Re-Ingestion & Verification**:
  - Implemented `scripts/run_full_ingestion.py` and re-ingested the full 30-document standards corpus into `domain_copilot` using local Ollama (`nomic-embed-text`), populating 30 documents, 497 chunks, and 497 embeddings. Verified idempotency (0 new rows on re-run).
  - Verified NASSCOM PDF extraction: 0 chunks contained the bare `QG-03` header, and standard ID `SSC/N0506` was correctly extracted.
  - Ran full test suite (62 items: 57 passed, 5 xfailed) and confirmed dev DB row counts remained at exactly 30 documents and 497 chunks post-test.
- **CI Test Database Provisioning and TSVECTOR ORM Model Alignment**:
  - In GitHub Actions CI runner environments, tests failed with `FATAL: database "domain_copilot_test" does not exist`. The PostgreSQL service container was initialized with `POSTGRES_DB: domain_copilot`, while `ci.yml` only set `DATABASE_URL` (using dynamic port `${{ job.services.postgres.ports[5432] }}`) without creating `domain_copilot_test` or setting `TEST_DATABASE_URL`.
  - Added a `Create test database` step in `.github/workflows/ci.yml` to run `CREATE DATABASE domain_copilot_test;` on the CI PostgreSQL instance, and explicitly set `TEST_DATABASE_URL` in the `Tests` step.
  - Created `backend/tests/db_test_utils.py` providing `get_test_db_url()` and `ensure_test_db_exists(db_url)`: derives the test database from `DATABASE_URL` when `TEST_DATABASE_URL` is omitted, and self-heals by connecting to any accessible maintenance database (`postgres`, `domain_copilot`, or `template1`) to auto-create `domain_copilot_test` if missing.
  - Added `search_vector = Column(TSVECTOR, Computed("to_tsvector('english', content)", persisted=True))` and `Index("ix_chunk_search_vector", "search_vector", postgresql_using="gin")` to `Chunk` in `backend/infrastructure/db/models.py`. This ensures fresh test databases constructed via `Base.metadata.create_all(engine)` contain the stored `search_vector` column and GIN index required by `PgKeywordSearch`.


