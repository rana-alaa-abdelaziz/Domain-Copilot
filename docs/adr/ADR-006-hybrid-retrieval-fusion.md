# ADR-006: Hybrid Retrieval Fusion Method

## Status
Accepted

## Context
FR-2 requires hybrid retrieval (dense + keyword) with a documented
fusion method, and correct refusal on low-evidence questions.

## Decision

**Fusion method**: Reciprocal Rank Fusion (RRF), k=60 — the standard
constant from Cormack, Clarke & Buettcher (2009), used unchanged since
it's the widely-adopted default in hybrid search implementations and
dampens the effect of small rank differences at the top of either list.
Formula: for each chunk, score = 1/(60+rank) summed across whichever of
the two result lists (dense, keyword) it appears in.

**Dense side**: pgvector cosine similarity against chunk embeddings.
**Keyword side**: Postgres full-text search (tsvector/websearch_to_tsquery)
against the same chunk table — no separate search engine, consistent
with the single-database decision in ADR-005.

**Minimum similarity floor (added after first real eval run)**: dense
search enforces a 0.3 minimum cosine similarity before a result is
considered a candidate at all. This was not part of the original design
— it was added after scripts/eval.py's first real run showed 0%
refusal correctness on adversarial (out-of-corpus) questions. Root
cause: cosine similarity search has no native "no match" concept, so it
always returns its k nearest vectors regardless of actual relevance,
and RRF's rank-based scoring can't distinguish "the best of five
genuinely relevant chunks" from "the least-bad of five irrelevant ones."
See docs/EVALUATION.md for the full before/after numbers.

## Alternatives Considered

**Weighted linear combination of raw scores** (e.g., 0.5*dense_score +
0.5*keyword_score): rejected. Postgres ts_rank and cosine similarity are
on different, not-directly-comparable scales (ts_rank is described in
Postgres's own docs as "roughly 0-1 in practice but not guaranteed");
combining raw magnitudes would require score normalization that adds
complexity without a clear correctness benefit over rank-based fusion.

**A single retrieval-score threshold applied to the keyword side too**
(mirroring the dense-side fix): considered, then rejected for now. Postgres
full-text search's WHERE clause already only returns genuine lexical
matches (unlike dense search's always-return-top-k behavior) — one
remaining eval failure (q21, "Is it good?") is a real keyword match on a
common word, not a scoring bug, and no principled ts_rank threshold
reliably separates "coincidental single-word match" from "a real short
query" without risking false negatives on legitimate short queries.
Documented as an accepted limitation in docs/EVALUATION.md instead of a
forced, unprincipled fix.

## Consequences
- Fusion logic is pure domain code (domain/services/retrieval_fusion.py),
  no SQLAlchemy/DB dependency, fully unit-testable in isolation.
- The 0.3 similarity floor is a heuristic calibrated from one real run's
  score distribution, not a formally derived value — flagged for
  recalibration as the corpus grows (see code comment in
  infrastructure/vectorstore/pgvector_store.py).
- Ambiguous-query detection (q21-style failures) is explicitly out of
  scope for retrieval alone; tracked as a gap-table row pending an
  agent/generation layer.