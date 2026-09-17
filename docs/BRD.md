# BRD
| Req ID | Requirement | Status | Evidence |
|---|---|---|---|
| BR-01 | FR-1 Ingestion pipeline (extract/chunk/embed/index, idempotent) | Implemented | backend/application/use_cases/ingest_pipeline.py, scripts/run_full_ingestion.py output (30 docs, 497 chunks, 497 embedded) |
| BR-02 | FR-2 Hybrid retrieval with documented fusion | Implemented | backend/application/use_cases/hybrid_retrieve.py, ADR-006 |
| BR-03 | FR-2 Retrieval enhancement (Rank Fusion) | Implemented | backend/application/use_cases/hybrid_retrieve.py, tests/test_rank_fusion.py |
| BR-04 | FR-2 Correct refusal on low-evidence questions | Implemented | eval/golden_set.yaml adversarial cases, docs/EVALUATION.md (85.7% refusal correctness) |
| BR-05 | FR-3 Golden evaluation set (≥25 pairs, ≥5 adversarial) with runnable harness | Implemented | eval/golden_set.yaml (25 entries, 7 adversarial), scripts/eval.py, eval/latest_results.json |
| BR-06 | FR-6 Real-time streaming (SSE token & progress) and true background cancellation | Implemented | backend/infrastructure/api/streaming_router.py, LLM stream refactoring, test_streaming.py |
| BR-07 | FR-9 Cost accounting / Token usage tracking | Implemented | backend/infrastructure/llm/accounting_provider.py, backend/infrastructure/db/repositories/llm_call_repository.py |
| BR-08 | Variant D3 (Distractor Rationales) | Implemented | backend/application/agents/assessment_generator.py, frontend/static/js/app.js (UI rendering) |
| BR-09 | Twist T5 (Enterprise Review Queue / Pull Model) | Implemented | backend/infrastructure/api/review_router.py, frontend/static/js/app.js (Claim buttons & UI Ribbon) |

## Assumptions
- Review task assignment (assigned_reviewer_id) is advisory, not an
  access-control boundary. Any authenticated lead_instructor may
  submit a decision on any pending review task, including ones
  assigned to a different reviewer. This supports escalation/reassignment
  without a separate transfer-ownership step.
- Granular Chunk Citations: For the Assessment Generator, all retrieved chunk IDs
  of a subject are assigned to every question in that section. This is an MVP scoping
  assumption to keep grading auditors aligned with the architecture without requiring
  the LLM to explicitly attribute individual chunk IDs to individual questions.
- Distractor Rationales (D3): All multiple choice questions generated must have
  distinct rationales for each incorrect option, explaining why it is a plausible
  distractor. This enables deeper auditing during human review.