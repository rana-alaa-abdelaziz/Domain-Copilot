"""SQLAlchemy implementation of ReviewTaskRepository."""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.domain.entities.review_task import ReviewTask as DomainReviewTask
from backend.domain.ports.review_task_repository import ReviewTaskRepository
from backend.infrastructure.db.models import ReviewTask as OrmReviewTask
from backend.infrastructure.db.models import ReviewTaskStatusEnum


class SqlAlchemyReviewTaskRepository(ReviewTaskRepository):
    def __init__(self, session: Session, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    def create(
        self, thread_id: str, item_id: str, target_role: str,
        priority: str, sla_due_at: datetime,
    ) -> DomainReviewTask:
        orm_task = OrmReviewTask(
            thread_id=thread_id,
            item_id=item_id,
            target_role=target_role,
            priority=priority,
            sla_due_at=sla_due_at,
        )
        self._session.add(orm_task)
        if self._auto_commit:
            self._session.commit()
        else:
            self._session.flush()
        return self._to_domain(orm_task)

    def get_by_thread_id(self, thread_id: str) -> DomainReviewTask | None:
        orm_task = (
            self._session.query(OrmReviewTask)
            .filter(OrmReviewTask.thread_id == thread_id)
            .first()
        )
        return self._to_domain(orm_task) if orm_task else None

    def list_pending(self, assigned_reviewer_id: str | None = None) -> list[DomainReviewTask]:
        query = self._session.query(OrmReviewTask).filter(
            OrmReviewTask.status.in_(
                [ReviewTaskStatusEnum.PENDING, ReviewTaskStatusEnum.IN_REVIEW]
            )
        )
        if assigned_reviewer_id is not None:
            query = query.filter(OrmReviewTask.assigned_reviewer_id == assigned_reviewer_id)
        query = query.order_by(
            OrmReviewTask.priority.asc(), OrmReviewTask.sla_due_at.asc()
        )
        return [self._to_domain(t) for t in query.all()]

    def assign(self, review_task_id: str, reviewer_id: str) -> None:
        orm_task = self._session.get(OrmReviewTask, review_task_id)
        if orm_task is None:
            raise ValueError(f"No review_task found with id={review_task_id}")
        orm_task.assigned_reviewer_id = reviewer_id
        orm_task.status = ReviewTaskStatusEnum.IN_REVIEW
        if self._auto_commit:
            self._session.commit()

    def update_status(
        self, review_task_id: str, status: str, comment: str | None = None
    ) -> None:
        orm_task = self._session.get(OrmReviewTask, review_task_id)
        if orm_task is None:
            raise ValueError(f"No review_task found with id={review_task_id}")
        orm_task.status = status
        if comment is not None:
            orm_task.comment = comment
        if self._auto_commit:
            self._session.commit()

    def list_overdue(self) -> list[DomainReviewTask]:
        now = datetime.now(timezone.utc)
        query = self._session.query(OrmReviewTask).filter(
            and_(
                OrmReviewTask.sla_due_at < now,
                OrmReviewTask.status.in_(
                    [ReviewTaskStatusEnum.PENDING, ReviewTaskStatusEnum.IN_REVIEW]
                ),
            )
        )
        return [self._to_domain(t) for t in query.all()]

    @staticmethod
    def _to_domain(orm_task: OrmReviewTask) -> DomainReviewTask:
        return DomainReviewTask(
            review_task_id=orm_task.review_task_id,
            thread_id=orm_task.thread_id,
            item_id=orm_task.item_id,
            target_role=orm_task.target_role,
            status=orm_task.status.value if hasattr(orm_task.status, "value") else orm_task.status,
            priority=orm_task.priority.value if hasattr(orm_task.priority, "value") else orm_task.priority,
            sla_due_at=orm_task.sla_due_at,
            assigned_reviewer_id=orm_task.assigned_reviewer_id,
            comment=orm_task.comment,
            created_at=orm_task.created_at,
            updated_at=orm_task.updated_at,
        )
    def get_reviewer_stats(self) -> dict[str, Any]:
        """Aggregates review metrics grouped by assigned reviewer."""
        from sqlalchemy import func

        from backend.infrastructure.db.models import ReviewTaskStatusEnum

        rows = self._session.query(
            OrmReviewTask.assigned_reviewer_id,
            func.count(OrmReviewTask.review_task_id).label("total_tasks"),
            func.sum(func.case((OrmReviewTask.status == ReviewTaskStatusEnum.APPROVED, 1), else_=0)).label("approved_count"),
            func.sum(func.case((OrmReviewTask.status == ReviewTaskStatusEnum.REJECTED, 1), else_=0)).label("rejected_count"),
            func.sum(func.case((OrmReviewTask.status.in_([ReviewTaskStatusEnum.EDITED_APPROVED]), 1), else_=0)).label("edited_count"),
        ).group_by(OrmReviewTask.assigned_reviewer_id).all()

        stats = {}
        for row in rows:
            reviewer = row.assigned_reviewer_id or "unassigned"
            total = row.total_tasks or 0
            approved = row.approved_count or 0
            rejected = row.rejected_count or 0
            edited = row.edited_count or 0
            
            approval_rate = (approved / total) * 100 if total > 0 else 0.0
            rejection_rate = (rejected / total) * 100 if total > 0 else 0.0

            stats[reviewer] = {
                "total_completed_or_processed": total,
                "approved": approved,
                "rejected": rejected,
                "edited_approved": edited,
                "approval_rate_percent": round(approval_rate, 2),
                "rejection_rate_percent": round(rejection_rate, 2),
            }
        return stats