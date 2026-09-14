| Target Component | Implemented? | Why Deferred | Interim Mitigation | Effort/Cost to Close |
|---|---|---|---|---|
| Full groundedness evaluation (generated answer checked against citations) | No | No answer-generation/agent use case exists yet — only retrieval is built | Retrieval-level proxy: check whether the top-ranked chunk itself contains expected keywords (scripts/eval.py) | ~2h once an answer-generation use case exists |
| Indirect prompt-injection resistance testing | No | Requires a generation step that reads chunk content into a prompt — none exists yet | Direct (query-level) injection cases only, in eval/golden_set.yaml (q23, q24) | ~1h to add indirect cases once agents/generation exist |
| Ambiguous-query detection at retrieval time | No | Retrieval can only score relevance, not judge whether a query itself is answerable/specific enough (see q21 in EVALUATION.md) | Documented as an accepted limitation; refusal relies on evidence scoring, not query-intent classification | Requires an agent/LLM-based query classifier — not scoped for this cycle |




=====================================




| Target Component | Implemented? | Why Deferred | Interim Mitigation | Effort/Cost to Close |
|---|---|---|---|---|
| Strict msgpack serialization for LangGraph checkpointer state | No (using default, non-strict serialization) | LangGraph's checkpointer (MemorySaver, and any future persistent checkpointer) serializes WorkflowState via msgpack. Because the state holds custom Pydantic domain models (CompetencyGapReport, ModuleOutlineReport, AssessmentItemReport) rather than plain dicts/primitives, msgpack currently falls back to permissive handling and emits "deserializing unregistered type" warnings. LangGraph has signaled this will become strict in a future version, which would break checkpoint restoration outright rather than just warn. | None needed today — checkpoint save/restore is fully functional; verified end-to-end (6 competency gaps correctly recovered from a Postgres-backed checkpoint after restart). Warnings are non-blocking. | ~2-3h: register the three Pydantic models with LangGraph's `allowed_msgpack_modules` (or equivalent custom serializer config), OR convert WorkflowState's stored values to plain dicts before checkpointing (already partially done in nodes.py, which stores gap_report as a dict, not the raw dataclass) and reconstruct the typed object only on read. Second option requires no LangGraph-version-specific config and is more future-proof, at the cost of an explicit serialize/deserialize step in the node wrapper. |