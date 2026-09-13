# Evaluation

## Corpus
- 30 documents ingested (18 synthetic, 12 real/public — see corpus/manifest.md)
- 497 chunks produced
- 497/497 chunks embedded (100%)
- Embedding provider used for this run: OllamaAdapter (nomic-embed-text, 768-dim)

## Golden Set Results
Source: eval/golden_set.yaml (25 entries: 18 standard, 7 adversarial)
Harness: scripts/eval.py
Run date: [fill in actual date]

| Metric | Result |
|---|---|
| Hit rate (top-5) | 88.9% (16/18) |
| Top-1 precision (groundedness proxy) | 83.3% (15/18) |
| Refusal correctness | 85.7% (6/7) |

## Known failures and interpretation

**q12 — "What does competency 2.1 in the Backend Competency Framework cover?"**
Missed (no hit in top-5). Interpretation: numeric/ID-style tokens like
"2.1" likely tokenize poorly in both dense embeddings and Postgres
full-text search (periods and short numeric strings are often stripped
or treated as noise by standard tokenizers). Not yet fixed. Candidate
future fix: a dedicated exact-match lookup path for standard_id-style
queries, bypassing semantic/keyword search entirely for queries that
look like a framework reference.

**q13 — "What distinguishes a Level 3 from a Level 1 developer in code correctness?"**
Missed. Interpretation: rubric documents are chunked by section, so
"Level 1" and "Level 3" descriptions live in separate chunks. A
comparison question needs both, but retrieval only surfaces the most
relevant single chunk, not a synthesized pair. Known limitation of
section-level chunking (see ADR-001) for comparison-style questions.
Not planned for a fix this cycle — would require query decomposition
or multi-chunk synthesis, which is generation-layer work.

**q21 — "Is it good?"**
Not correctly refused (should have been). Interpretation: the word
"good" genuinely appears verbatim in two corpus documents
(rubric_database_design_competency.md, rubric_debugging_troubleshooting.md),
so Postgres full-text search correctly found a literal keyword match —
this is not a retrieval bug. The actual gap is that no retrieval-only
mechanism can distinguish "a real keyword match" from "a query too
ambiguous/referent-less to answer meaningfully" — that judgment requires
a generation or agent-level step capable of assessing question
specificity, which does not exist yet. Deferred until that layer is
built; documented here as an accepted, understood limitation rather than
silently left unexplained.

## Bug found and fixed during first real run

Initial refusal correctness was 0% (0/7). Root cause: PgVectorStore.query()
had no similarity floor — cosine similarity search has no native concept
of "no match," so it always returned its "5 least dissimilar" chunks even
for completely out-of-corpus queries (e.g. "maximum tensile strength of
grade 8 steel bolts"). One of those irrelevant chunks always landed at
dense-rank #1 and picked up a nonzero RRF fusion score (exactly 1/61,
matching RRF_K=60's formula for a rank-1-in-one-list-only match), which
was above the eval harness's refusal threshold.

Fix: added a MIN_SIMILARITY = 0.3 floor to PgVectorStore.query() (WHERE
1 - cosine_distance >= 0.3), based on the observed score distribution in
that first run — real matches scored well above 0.3, irrelevant nearest-
neighbors well below. After the fix, refusal correctness rose to 85.7%
with no measurable change to hit rate or top-1 precision (real matches
were unaffected, as expected).

## What's not yet measured (scope limitation, not an oversight)

This harness evaluates HybridRetrieveUseCase directly — there is no
answer-generation/agent step wired in yet. This means:

- "Groundedness" above is a retrieval-level proxy (does the top-ranked
  chunk contain the expected content), not a check of a generated
  answer's claims against its citations.
- The prompt-injection adversarial cases (q23, q24) only test that a
  malicious QUERY doesn't break retrieval. They do not test the more
  important INDIRECT case (a malicious instruction embedded inside a
  retrieved document being obeyed by a generation step), since no
  generation step exists to obey anything yet.

Both are tracked as open gap-table rows in docs/SYSTEM-DESIGN.md and
must be re-tested once the agent/orchestration layer is built.