from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.domain.entities.published_curriculum import PublishedCurriculum
from backend.domain.ports.published_curriculum_repository import (
    PublishedCurriculumRepository,
)
from backend.infrastructure.db.models import (
    PublishedCurriculum as OrmPublishedCurriculum,
)


class SqlAlchemyPublishedCurriculumRepository(PublishedCurriculumRepository):
    def __init__(self, session: Session, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    def save(
        self,
        thread_id: str,
        target_role: str,
        module_outline: dict[str, Any],
        assessment_items: dict[str, Any],
        approved_by: str,
    ) -> PublishedCurriculum:
        # Check for idempotency: if it already exists, just return it.
        existing = self.get_by_thread_id(thread_id)
        if existing:
            return existing

        orm_pub = OrmPublishedCurriculum(
            thread_id=thread_id,
            target_role=target_role,
            module_outline=module_outline,
            assessment_items=assessment_items,
            approved_by=approved_by,
        )
        self._session.add(orm_pub)
        try:
            if self._auto_commit:
                self._session.commit()
            else:
                self._session.flush()
        except IntegrityError:
            self._session.rollback()
            # If there was a race condition, get the existing one
            existing = self.get_by_thread_id(thread_id)
            if existing:
                return existing
            raise

        return self._to_domain(orm_pub)

    def get_by_thread_id(self, thread_id: str) -> PublishedCurriculum | None:
        orm_pub = (
            self._session.query(OrmPublishedCurriculum)
            .filter(OrmPublishedCurriculum.thread_id == thread_id)
            .first()
        )
        return self._to_domain(orm_pub) if orm_pub else None

    @staticmethod
    def _to_domain(orm_pub: OrmPublishedCurriculum) -> PublishedCurriculum:
        return PublishedCurriculum(
            published_id=orm_pub.published_id,
            thread_id=orm_pub.thread_id,
            target_role=orm_pub.target_role,
            module_outline=orm_pub.module_outline,
            assessment_items=orm_pub.assessment_items,
            approved_by=orm_pub.approved_by,
            published_at=orm_pub.published_at,
        )
