"""
Port for ReviewTask persistence — the mechanism that makes T5's review
queue an actual queryable product, not just a label inside a LangGraph
checkpoint blob nobody can list without already knowing a thread_id.
"""
from abc import ABC, abstractmethod
from datetime import datetime

from backend.domain.entities.review_task import ReviewTask


class ReviewTaskRepository(ABC):
    @abstractmethod
    def create(
        self, thread_id: str, item_id: str, target_role: str,
        priority: str, sla_due_at: datetime,
    ) -> ReviewTask:
        """Creates a new review task with status='pending', unassigned."""

    @abstractmethod
    def get_by_thread_id(self, thread_id: str) -> ReviewTask | None:
        """Looks up the review task gating a given workflow thread."""

    @abstractmethod
    def list_pending(self, assigned_reviewer_id: str | None = None) -> list[ReviewTask]:
        """Lists tasks in 'pending' or 'in_review' status, optionally
        filtered to one reviewer — this is what a real queue UI/endpoint
        calls, unlike the current API which requires an already-known
        thread_id."""

    @abstractmethod
    def assign(self, review_task_id: str, reviewer_id: str) -> None:
        """Assigns a task to a reviewer, moving status to 'in_review'."""

    @abstractmethod
    def update_status(
        self, review_task_id: str, status: str, comment: str | None = None
    ) -> None:
        """Records the terminal decision (or 'escalated')."""

    @abstractmethod
    def list_overdue(self) -> list[ReviewTask]:
        """Tasks past sla_due_at still in 'pending'/'in_review' —
        input to the escalation job."""