"""
Plain domain entity for a human review task — the T5 "full product"
review queue: assignment, priority, SLA, status lifecycle,
approve/reject/edit-with-comment. No SQLAlchemy, no LangGraph imports.
"""
from dataclasses import dataclass
from datetime import datetime

REVIEW_TASK_STATUSES = {
    "pending", "in_review", "approved", "rejected", "edited_approved", "escalated",
}


@dataclass
class ReviewTask:
    review_task_id: str
    thread_id: str  
    item_id: str
    target_role: str
    status: str
    priority: str
    sla_due_at: datetime
    created_at: datetime
    updated_at: datetime
    assigned_reviewer_id: str | None = None
    comment: str | None = None