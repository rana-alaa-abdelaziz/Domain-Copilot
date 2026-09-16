# BRD
| Req ID | Requirement | Status | Evidence |
|---|---|---|---|
| BR-01 | FR-1 Ingestion pipeline (extract/chunk/embed/index, idempotent) | Implemented | backend/application/use_cases/ingest_pipeline.py, scripts/run_full_ingestion.py output (30 docs, 497 chunks, 497 embedded) |
| BR-02 | FR-2 Hybrid retrieval with documented fusion | Implemented | backend/application/use_cases/hybrid_retrieve.py, ADR-006 |
| BR-03 | FR-2 Retrieval enhancement (one justified addition) | [Partial/Not started — fill in based on your actual status] | — |
| BR-04 | FR-2 Correct refusal on low-evidence questions | Implemented | eval/golden_set.yaml adversarial cases, docs/EVALUATION.md (85.7% refusal correctness) |
| BR-05 | FR-3 Golden evaluation set (≥25 pairs, ≥5 adversarial) with runnable harness | Implemented | eval/golden_set.yaml (25 entries, 7 adversarial), scripts/eval.py, eval/latest_results.json |
| BR-06 | FR-6 Real-time streaming (SSE token & progress) and true background cancellation | Implemented | backend/infrastructure/api/streaming_router.py, LLM stream refactoring, test_streaming.py |

## Assumptions
- Review task assignment (assigned_reviewer_id) is advisory, not an
  access-control boundary. Any authenticated lead_instructor may
  submit a decision on any pending review task, including ones
  assigned to a different reviewer. This supports escalation/reassignment
  without a separate transfer-ownership step.