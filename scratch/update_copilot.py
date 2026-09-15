
with open(r'backend/infrastructure/orchestration/copilot_graph.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix imports
content = content.replace(
    'import time\nfrom concurrent.futures import ThreadPoolExecutor\nfrom concurrent.futures import TimeoutError as FutureTimeoutError\nfrom typing import TypedDict',
    '''import operator
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Annotated, TypedDict

from langchain_core.runnables import RunnableConfig'''
)

content = content.replace(
    'from backend.domain.errors.orchestration_errors import (\n    AgentTimeoutError,\n    MaxIterationsExceededError,\n)',
    '''from backend.domain.errors.orchestration_errors import (
    AgentTimeoutError,
    MaxIterationsExceededError,
)
from backend.domain.ports.review_task_repository import ReviewTaskRepository
from backend.domain.services.review_priority import compute_priority, compute_sla_due_at'''
)

# Fix CopilotState
content = content.replace(
    '''    # Human-in-the-Loop review tracking & audit trail
    review_status: str | None
    audit_trail: dict[str, Any] | None''',
    '''    # Human-in-the-Loop review tracking & audit trail
    review_status: str | None
    audit_trail: Annotated[list[dict[str, Any]], operator.add]'''
)

# Fix create_copilot_graph signature
content = content.replace(
    '''    assessment_generator: AssessmentGenerator | None = None,
    checkpointer: PostgresSaver | None = None,
):''',
    '''    assessment_generator: AssessmentGenerator | None = None,
    checkpointer: PostgresSaver | None = None,
    review_task_repository: ReviewTaskRepository | None = None,
):'''
)

# Fix run_human_review
content = content.replace(
    '''    # --- HUMAN REVIEW BREAKPOINT NODE ---
    def run_human_review(state: CopilotState):
        """Passthrough node. Graph pauses BEFORE this node due to interrupt_before."""
        step_count = _check_iteration_cap(state)
        return {
            "step_count": step_count,
            "review_status": state.get("review_status", "approved"),
        }''',
    '''    # --- HUMAN REVIEW BREAKPOINT NODE ---
    def run_human_review(state: CopilotState, config: RunnableConfig):
        """Passthrough node. Graph pauses BEFORE this node due to interrupt_before."""
        step_count = _check_iteration_cap(state)

        if review_task_repository is not None:
            gap_report = state.get("competency_gap_report")
            thread_id = config.get("configurable", {}).get("thread_id")
            existing = review_task_repository.get_by_thread_id(thread_id) if thread_id else None
            if existing is None and gap_report is not None and thread_id:
                priority = compute_priority(gap_report)
                review_task_repository.create(
                    thread_id=thread_id,
                    item_id=thread_id,
                    target_role=state.get("target_role", ""),
                    priority=priority,
                    sla_due_at=compute_sla_due_at(priority),
                )

        return {
            "step_count": step_count,
            "review_status": state.get("review_status", "approved"),
        }'''
)

with open(r'backend/infrastructure/orchestration/copilot_graph.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated copilot_graph.py')
