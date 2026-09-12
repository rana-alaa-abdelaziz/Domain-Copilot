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
