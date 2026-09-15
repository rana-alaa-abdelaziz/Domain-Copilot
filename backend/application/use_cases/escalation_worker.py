"""
Background worker use case to periodically check overdue review tasks
via list_overdue() and automatically transition their status to 'escalated'.
"""
import logging

from backend.domain.ports.review_task_repository import ReviewTaskRepository

logger = logging.getLogger(__name__)


class EscalationWorkerUseCase:
    def __init__(self, review_task_repository: ReviewTaskRepository):
        self._repo = review_task_repository

    def execute(self) -> int:
        """
        Finds all overdue pending review tasks and marks them as escalated.
        Returns the count of newly escalated tasks.
        """
        overdue_tasks = self._repo.list_overdue()
        escalated_count = 0

        for task in overdue_tasks:
            if task.status == "pending":
                try:
                    self._repo.update_status(task.review_task_id, "escalated")
                    escalated_count += 1
                    logger.info(
                        f"Review task {task.review_task_id} for thread '{task.thread_id}' "
                        f"has been automatically escalated due to SLA expiration."
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        f"Failed to escalate review task {task.review_task_id}: {exc}"
                    )

        return escalated_count