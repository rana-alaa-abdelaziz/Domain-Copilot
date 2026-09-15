from abc import ABC, abstractmethod
from typing import Any

from backend.domain.entities.published_curriculum import PublishedCurriculum


class PublishedCurriculumRepository(ABC):
    @abstractmethod
    def save(
        self,
        thread_id: str,
        target_role: str,
        module_outline: dict[str, Any],
        assessment_items: dict[str, Any],
        approved_by: str,
    ) -> PublishedCurriculum:
        pass

    @abstractmethod
    def get_by_thread_id(self, thread_id: str) -> PublishedCurriculum | None:
        pass
