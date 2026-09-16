from abc import ABC, abstractmethod

from backend.domain.entities.llm_call_record import LlmCallRecord


class LlmCallRepository(ABC):
    @abstractmethod
    def save(self, record: LlmCallRecord) -> None: ...

    @abstractmethod
    def list_by_correlation_id(self, correlation_id: str) -> list[LlmCallRecord]: ...

    @abstractmethod
    def list_by_thread_id(self, thread_id: str) -> list[LlmCallRecord]: ...

    @abstractmethod
    def get_totals_by_thread_id(self, thread_id: str) -> dict: ...
