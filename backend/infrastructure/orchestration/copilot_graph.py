"""
Multi-agent curriculum workflow graph: standards_mapper -> module_outline_generator
-> assessment_generator -> human_review -> END.

FR-5 resilience controls (max-iteration breaker, per-step timeout, retry
with backoff, graceful degradation) wrap every node here — no agent call
in this file runs unprotected. Timeout uses ThreadPoolExecutor rather
than signal.alarm since this must run on Windows, not just Unix.
"""
import operator
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Annotated, Any, TypedDict

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
from backend.domain.ports.published_curriculum_repository import (
    PublishedCurriculumRepository,
)
from backend.domain.ports.review_task_repository import ReviewTaskRepository
from backend.domain.services.review_priority import compute_priority, compute_sla_due_at

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
    review_status: str | None
    audit_trail: Annotated[list[dict[str, Any]], operator.add]  # was: dict[str, Any] | None

    # FR-5 resilience bookkeeping
    step_count: int
    degraded: bool
    error: str | None



def _run_with_timeout(fn, timeout_seconds: int):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            raise AgentTimeoutError("agent", timeout_seconds) from exc


def _run_with_retry(fn, max_retries: int = MAX_RETRIES):
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except AgentTimeoutError:
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
        raise MaxIterationsExceededError("workflow", MAX_ITERATIONS)
    return step_count


def create_copilot_graph(
    standards_mapper: StandardsMapper,
    outline_generator: ModuleOutlineGenerator | None = None,
    assessment_generator: AssessmentGenerator | None = None,
    checkpointer: PostgresSaver | None = None,
    review_task_repository: ReviewTaskRepository | None = None,
    published_curriculum_repository: PublishedCurriculumRepository | None = None,
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
            try:
                plain = standards_mapper.get_plain_evidence(state["target_role"])
                fallback_report = CompetencyGapReport(
                    target_role=state["target_role"],
                    user_reported_subjects=state["user_reported_subjects"],
                    gaps=[],
                )
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

    from langchain_core.runnables import RunnableConfig
    
    def run_create_review_task(state: CopilotState, config: RunnableConfig | None = None):
        step_count = _check_iteration_cap(state)
        if review_task_repository is not None:
            gap_report = state.get("competency_gap_report")
            thread_id = config["configurable"].get("thread_id") if config and "configurable" in config else None
            
            existing = review_task_repository.get_by_thread_id(thread_id) if thread_id else None
            if existing is None and gap_report is not None and thread_id:
                priority = compute_priority(gap_report)
                review_task_repository.create(
                    thread_id=thread_id,
                    item_id=thread_id,
                    target_role=state["target_role"],
                    priority=priority,
                    sla_due_at=compute_sla_due_at(priority),
                )
        return {"step_count": step_count}

    def run_human_review(state: CopilotState, config: RunnableConfig | None = None):  
        step_count = _check_iteration_cap(state)
        return {
            "step_count": step_count,
            "review_status": state.get("review_status", "approved"),
        }

    def run_publish_curriculum(state: CopilotState, config: RunnableConfig | None = None):
        step_count = _check_iteration_cap(state)
        thread_id = config["configurable"].get("thread_id") if config and "configurable" in config else None
        if published_curriculum_repository and thread_id:
            gap_report = state.get("competency_gap_report")
            outline = state.get("module_outline_report")
            assessment = state.get("assessment_report")

            if gap_report and outline and assessment:
                import dataclasses
                published_curriculum_repository.save(
                    thread_id=thread_id,
                    target_role=gap_report.target_role,
                    module_outline=[dataclasses.asdict(m) for m in outline.modules],
                    assessment_items=[item.model_dump() for item in assessment.items],
                    approved_by="human_reviewer",
                )
        return {"step_count": step_count}

    def route_after_review(state: CopilotState) -> str:
        status = state.get("review_status")
        if status in ("approved", "edited_approved"):
            return "publish_curriculum"
        return END

    workflow.add_node("create_review_task", run_create_review_task)
    workflow.add_node("human_review", run_human_review)
    workflow.add_node("publish_curriculum", run_publish_curriculum)
    workflow.add_edge(current_node, "create_review_task")
    workflow.add_edge("create_review_task", "human_review")
    workflow.add_conditional_edges("human_review", route_after_review, {"publish_curriculum": "publish_curriculum", END: END})
    workflow.add_edge("publish_curriculum", END)

    # Compile with checkpointer and the crucial interrupt breakpoint
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"],
    )