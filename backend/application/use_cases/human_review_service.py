"""
Human-in-the-Loop Review Service — decisions (approve, reject,
edit_with_comment), now backed by a real, queryable ReviewTaskRepository
instead of only a label inside a LangGraph checkpoint.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from backend.domain.ports.published_curriculum_repository import (
    PublishedCurriculumRepository,
)
from backend.domain.ports.review_task_repository import ReviewTaskRepository
from backend.domain.ports.workflow_graph import WorkflowGraphPort

logger = logging.getLogger(__name__)


class HumanReviewService:
    def __init__(
        self,
        graph: WorkflowGraphPort,
        review_task_repository: ReviewTaskRepository,
        published_curriculum_repository: PublishedCurriculumRepository | None = None,
    ):
        self.graph = graph
        self._review_tasks = review_task_repository
        self._published_curriculum = published_curriculum_repository

    def get_pending_review(self, thread_id: str) -> dict[str, Any]:
        thread_config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.get_state(thread_config)

        if not state or "human_review" not in state.next:
            return {"thread_id": thread_id, "status": "not_pending", "next_nodes": state.next if state else [], "values": {}}

        review_task = self._review_tasks.get_by_thread_id(thread_id)

        return {
            "thread_id": thread_id,
            "status": "pending_review",
            "target_role": state.values.get("target_role"),
            "user_reported_subjects": state.values.get("user_reported_subjects"),
            "competency_gap_report": state.values.get("competency_gap_report"),
            "module_outline_report": state.values.get("module_outline_report"),
            "assessment_report": state.values.get("assessment_report"),
            "review_task": review_task,  # priority, SLA, assignment — the T5 queue fields
        }

    def process_review_decision(
        self,
        thread_id: str,
        action: str,
        instructor_comment: str | None = None,
        edited_artifacts: dict[str, Any] | None = None,
        reviewer_id: str = "system_auto_assign",
    ) -> dict[str, Any]:
        thread_config = {"configurable": {"thread_id": thread_id}}
        current_state = self.graph.get_state(thread_config)

        if not current_state or "human_review" not in current_state.next:
            raise ValueError(f"Thread '{thread_id}' is not currently paused at a human review breakpoint.")

        if action not in {"approve", "reject", "edit_with_comment"}:
            raise ValueError(f"Invalid review action '{action}'. Must be 'approve', 'reject', or 'edit_with_comment'.")

        timestamp = datetime.now(timezone.utc).isoformat()
        audit_entry = {"action": action, "instructor_comment": instructor_comment, "timestamp": timestamp}
        logger.info(f"Audit Log [Thread {thread_id}]: Instructor action '{action}' recorded at {timestamp}.")

        review_task = self._review_tasks.get_by_thread_id(thread_id)
        status_map = {"approve": "approved", "reject": "rejected", "edit_with_comment": "edited_approved"}
        domain_status = status_map[action]

        if review_task is not None:
            if review_task.status == "pending":
                self._review_tasks.assign(review_task.review_task_id, reviewer_id=reviewer_id)
            self._review_tasks.update_status(
                review_task.review_task_id, status=domain_status, comment=instructor_comment
            )

        # audit_trail is a list with an operator.add reducer in CopilotState
        # (see copilot_graph.py) — appending, not overwriting, so a thread's
        # full decision history survives even if it's reviewed more than once.
        if action == "reject":
            self.graph.update_state(thread_config, {"review_status": "rejected", "audit_trail": [audit_entry]})
            return {"thread_id": thread_id, "status": "rejected", "audit": audit_entry}

        update_payload: dict[str, Any] = {"review_status": domain_status, "audit_trail": [audit_entry]}
        if action == "edit_with_comment" and edited_artifacts:
            if "module_outline_report" in edited_artifacts:
                update_payload["module_outline_report"] = edited_artifacts["module_outline_report"]
            if "assessment_report" in edited_artifacts:
                update_payload["assessment_report"] = edited_artifacts["assessment_report"]

        self.graph.update_state(thread_config, update_payload)
        final_result = self.graph.invoke(None, thread_config)

        is_published = False
        published_id = None
        if self._published_curriculum:
            pub_record = self._published_curriculum.get_by_thread_id(thread_id)
            if pub_record:
                is_published = True
                published_id = pub_record.published_id

        return {
            "thread_id": thread_id,
            "status": "completed",
            "review_status": domain_status,
            "published": is_published,
            "published_id": published_id,
            "audit": audit_entry,
            "final_state": {
                "target_role": final_result.get("target_role"),
                "assessment_items_count": len(final_result.get("assessment_report").items) if final_result.get("assessment_report") else 0,
            },
        }