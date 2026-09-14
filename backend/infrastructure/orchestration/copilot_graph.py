"""
Multi-agent curriculum workflow graph: standards_mapper -> module_outline_generator
-> assessment_generator -> END.

FR-5 resilience controls (max-iteration breaker, per-step timeout, retry
with backoff, graceful degradation) wrap every node here — no agent call
in this file runs unprotected. Timeout uses ThreadPoolExecutor rather
than signal.alarm since this must run on Windows, not just Unix.

Degradation strategy differs by node, deliberately:
- standards_mapper: falls back to raw retrieval evidence (plain RAG),
  since it's the only step that queries directly against a user-supplied
  role rather than consuming a prior step's structured output.
- module_outline_generator / assessment_generator: on exhausted retries,
  the run continues to END with that stage's report set to None and
  `degraded=True` recorded — falling back to "raw evidence" doesn't make
  sense for a step whose input is already a structured report, not a
  free-text query. The graph completing without crashing, with the
  failure visible in state, is what "graceful degradation" means here.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TypedDict

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, StateGraph

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import (
    ModuleOutlineGenerator,
)
from backend.application.agents.standards_mapper import StandardsMapper
from backend.domain.entities import CompetencyGapReport
from backend.domain.entities.assessment_item import AssessmentItemReport
from backend.domain.entities.module_outline import ModuleOutlineReport
from backend.domain.errors.orchestration_errors import (
    AgentTimeoutError,
    MaxIterationsExceededError,
)

MAX_ITERATIONS = 10
STEP_TIMEOUT_SECONDS = 60
MAX_RETRIES = 2
RETRY_BACKOFF_BASE_SECONDS = 2


class CopilotState(TypedDict, total=False):
    target_role: str
    user_reported_subjects: list[str]
    competency_gap_report: CompetencyGapReport | None
    module_outline_report: ModuleOutlineReport | None
    assessment_report: AssessmentItemReport | None

    # FR-5 bookkeeping — not part of the original TypedDict, needed to
    # actually track and surface the resilience controls' outcomes.
    step_count: int
    degraded: bool
    error: str | None


def _run_with_timeout(fn, timeout_seconds: int):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise AgentTimeoutError(f"Agent exceeded {timeout_seconds}s timeout") from exc


def _run_with_retry(fn, max_retries: int = MAX_RETRIES):
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except AgentTimeoutError:
            # Timeouts are not retried — see nodes.py's original rationale:
            # retrying a slow call rarely helps and delays degradation.
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_retries:
                time.sleep(RETRY_BACKOFF_BASE_SECONDS * (2 ** attempt))
    if last_exc is not None:
         raise last_exc
    raise RuntimeError("Retry loop completed without executing function.")
def _check_iteration_cap(state: CopilotState) -> int:
    step_count = state.get("step_count", 0) + 1
    if step_count > MAX_ITERATIONS:
        raise MaxIterationsExceededError(f"Workflow exceeded {MAX_ITERATIONS} node executions")
    return step_count


def create_copilot_graph(
    standards_mapper: StandardsMapper,
    outline_generator: ModuleOutlineGenerator | None = None,
    assessment_generator: AssessmentGenerator | None = None,
    checkpointer: PostgresSaver | None = None,
):
    workflow = StateGraph(CopilotState)

    def run_standards_mapper(state: CopilotState):
        step_count = _check_iteration_cap(state)

        def _call():
            return standards_mapper.run(
                target_role=state["target_role"],
                user_reported_subjects=state["user_reported_subjects"],
            )

        try:
            report = _run_with_retry(lambda: _run_with_timeout(_call, STEP_TIMEOUT_SECONDS))
            return {
                "competency_gap_report": report,
                "step_count": step_count,
                "degraded": False,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            # Graceful degradation to plain RAG: fall back to raw
            # requirement-doc evidence rather than failing the run.
            try:
                plain = standards_mapper.get_plain_evidence(state["target_role"])
                fallback_report = CompetencyGapReport(
                    target_role=state["target_role"],
                    user_reported_subjects=state["user_reported_subjects"],
                    gaps=[],
                )
                # Plain-RAG citations aren't structured gaps — surfaced via
                # the error message instead of forcing them into a shape
                # CompetencyGapReport was never meant to hold.
                citation_summary = "; ".join(c.content[:100] for c in plain.citations[:3])
                error_message = f"{exc} | plain_rag_fallback_evidence: {citation_summary}"
            except Exception:  # noqa: BLE001
                fallback_report = None
                error_message = str(exc)

            return {
                "competency_gap_report": fallback_report,
                "step_count": step_count,
                "degraded": True,
                "error": error_message,
            }

    workflow.add_node("standards_mapper", run_standards_mapper)
    workflow.set_entry_point("standards_mapper")
    current_node = "standards_mapper"

    if outline_generator:

        def run_outline_generator(state: CopilotState):
            step_count = _check_iteration_cap(state)
            gap_report = state.get("competency_gap_report")

            if gap_report is None:
                # Upstream already degraded to no usable gap report —
                # nothing meaningful to build an outline from.
                return {
                    "module_outline_report": None,
                    "step_count": step_count,
                    "degraded": True,
                    "error": (state.get("error") or "") + " | outline skipped: no gap report",
                }

            def _call():
                return outline_generator.generate_outline(gap_report)

            try:
                outline_report = _run_with_retry(
                    lambda: _run_with_timeout(_call, STEP_TIMEOUT_SECONDS)
                )
                return {
                    "module_outline_report": outline_report,
                    "step_count": step_count,
                    "degraded": state.get("degraded", False),
                    "error": state.get("error"),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "module_outline_report": None,
                    "step_count": step_count,
                    "degraded": True,
                    "error": f"{state.get('error') or ''} | outline_generator failed: {exc}",
                }

        workflow.add_node("module_outline_generator", run_outline_generator)
        workflow.add_edge(current_node, "module_outline_generator")
        current_node = "module_outline_generator"

    if assessment_generator:

        def run_assessment_generator(state: CopilotState):
            step_count = _check_iteration_cap(state)
            gap_report = state.get("competency_gap_report")

            if gap_report is None:
                return {
                    "assessment_report": None,
                    "step_count": step_count,
                    "degraded": True,
                    "error": (state.get("error") or "") + " | assessment skipped: no gap report",
                }

            def _call():
                return assessment_generator.generate_items(gap_report)

            try:
                assessment_report = _run_with_retry(
                    lambda: _run_with_timeout(_call, STEP_TIMEOUT_SECONDS)
                )
                return {
                    "assessment_report": assessment_report,
                    "step_count": step_count,
                    "degraded": state.get("degraded", False),
                    "error": state.get("error"),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "assessment_report": None,
                    "step_count": step_count,
                    "degraded": True,
                    "error": f"{state.get('error') or ''} | assessment_generator failed: {exc}",
                }

        workflow.add_node("assessment_generator", run_assessment_generator)
        workflow.add_edge(current_node, "assessment_generator")
        current_node = "assessment_generator"

    workflow.add_edge(current_node, END)

    return workflow.compile(checkpointer=checkpointer)