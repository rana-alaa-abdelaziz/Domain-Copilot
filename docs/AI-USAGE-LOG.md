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