"""
Human-in-the-Loop Review Service for handling lead instructor decisions 
(approve, reject, edit_with_comment) with full audit logging.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


class HumanReviewService:
    def __init__(self, compiled_graph: CompiledStateGraph):
        self.graph = compiled_graph

    def get_pending_review(self, thread_id: str) -> dict[str, Any]:
        """Fetches the paused state and generated artifacts for a specific thread."""
        thread_config = {"configurable": {"thread_id": thread_id}}
        state = self.graph.get_state(thread_config)

        if not state or "human_review" not in state.next:
            return {
                "thread_id": thread_id,
                "status": "not_pending",
                "next_nodes": state.next if state else [],
                "values": {},
            }

        return {
            "thread_id": thread_id,
            "status": "pending_review",
            "target_role": state.values.get("target_role"),
            "user_reported_subjects": state.values.get("user_reported_subjects"),
            "competency_gap_report": state.values.get("competency_gap_report"),
            "module_outline_report": state.values.get("module_outline_report"),
            "assessment_report": state.values.get("assessment_report"),
        }

    def process_review_decision(
        self,
        thread_id: str,
        action: str,
        instructor_comment: str | None = None,
        edited_artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Processes lead instructor decision: 'approve', 'reject', or 'edit_with_comment'.
        Records audit logs and resumes or terminates graph execution.
        """
        thread_config = {"configurable": {"thread_id": thread_id}}
        current_state = self.graph.get_state(thread_config)

        if not current_state or "human_review" not in current_state.next:
            raise ValueError(f"Thread '{thread_id}' is not currently paused at a human review breakpoint.")

        timestamp = datetime.now(timezone.utc).isoformat()
        audit_entry = {
            "action": action,
            "instructor_comment": instructor_comment,
            "timestamp": timestamp,
        }
        logger.info(f"Audit Log [Thread {thread_id}]: Instructor action '{action}' recorded at {timestamp}.")

        if action == "reject":
            self.graph.update_state(
                thread_config,
                {
                    "review_status": "rejected",
                    "audit_trail": audit_entry,
                },
            )
            return {"thread_id": thread_id, "status": "rejected", "audit": audit_entry}

        elif action == "edit_with_comment":
            update_payload: dict[str, Any] = {
                "review_status": "approved_with_edits",
                "audit_trail": audit_entry,
            }
            if edited_artifacts:
                if "module_outline_report" in edited_artifacts:
                    update_payload["module_outline_report"] = edited_artifacts["module_outline_report"]
                if "assessment_report" in edited_artifacts:
                    update_payload["assessment_report"] = edited_artifacts["assessment_report"]

            self.graph.update_state(thread_config, update_payload)

        elif action == "approve":
            self.graph.update_state(
                thread_config,
                {
                    "review_status": "approved",
                    "audit_trail": audit_entry,
                },
            )
        else:
            raise ValueError(f"Invalid review action '{action}'. Must be 'approve', 'reject', or 'edit_with_comment'.")

        # Resume graph execution past the human_review breakpoint to completion
        final_result = self.graph.invoke(None, thread_config)
        
        return {
            "thread_id": thread_id,
            "status": "completed",
            "review_status": action,
            "audit": audit_entry,
            "final_state": {
                "target_role": final_result.get("target_role"),
                "assessment_items_count": len(final_result.get("assessment_report").items) if final_result.get("assessment_report") else 0,
            },
        }