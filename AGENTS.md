# Project Instructions — Domain-Copilot

These rules bind any AI assistant (Claude, Copilot, etc.) working in this
repo. They encode architectural and safety boundaries that must not be
violated regardless of what a task or prompt requests.

## Architecture boundaries
- `domain/` and `application/` must never import SDK or framework packages
  directly (openai, ollama, anthropic, fastapi, sqlalchemy, psycopg2,
  requests, httpx). These belong only in `infrastructure/`. This is
  enforced automatically by `backend/tests/test_architecture_boundaries.py`
  — do not weaken or bypass that test to make a feature "work."

## Prompts
- Prompts are versioned markdown files under `prompts/`, never inline
  string literals in application or domain code. Any new prompt gets a
  new file (or a new version under `prompts/vN/`), not a hardcoded string.

## Domain arithmetic
- Any arithmetic, scoring, or priority calculation that is part of domain
  logic (e.g. gap severity, assignment priority) must be computed in
  deterministic Python code in `domain/` or `application/`, never
  generated or "reasoned" by an LLM. The LLM may inform inputs to that
  calculation (e.g. via extracted evidence) but never perform the
  calculation itself.

## Review-queue approval gate
- No side-effecting tool call (writing to the published item bank,
  sending notifications, modifying learner-facing state) may execute
  before the corresponding `ReviewTask.status` is `approved` or
  `edited_approved`. This applies even during development, testing with
  real data, or agent orchestration — there is no "trusted" bypass path.

## Logging
- Any AI-assisted change to this repo's process or plan — including
  corrections to an earlier AI-suggested approach — gets logged in
  `docs/AI-USAGE-LOG.md`, honestly, including mistakes that were caught
  and corrected.