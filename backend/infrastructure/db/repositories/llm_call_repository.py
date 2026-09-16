from sqlalchemy.orm import Session

from backend.domain.entities.llm_call_record import LlmCallRecord
from backend.domain.ports.llm_call_repository import LlmCallRepository
from backend.infrastructure.db.models import LlmCallRecordModel


class SqlAlchemyLlmCallRepository(LlmCallRepository):
    def __init__(self, session: Session):
        self.session = session

    def save(self, record: LlmCallRecord) -> None:
        model = LlmCallRecordModel(
            call_id=record.call_id,
            correlation_id=record.correlation_id,
            thread_id=record.thread_id,
            agent_name=record.agent_name,
            provider=record.provider,
            model=record.model,
            prompt_tokens=record.prompt_tokens,
            completion_tokens=record.completion_tokens,
            estimated_cost_usd=record.estimated_cost_usd,
            created_at=record.created_at,
        )
        self.session.add(model)
        self.session.commit()

    def list_by_correlation_id(self, correlation_id: str) -> list[LlmCallRecord]:
        models = self.session.query(LlmCallRecordModel).filter_by(correlation_id=correlation_id).all()
        return [self._to_entity(m) for m in models]

    def list_by_thread_id(self, thread_id: str) -> list[LlmCallRecord]:
        models = self.session.query(LlmCallRecordModel).filter_by(thread_id=thread_id).all()
        return [self._to_entity(m) for m in models]

    def get_totals_by_thread_id(self, thread_id: str) -> dict:
        models = self.session.query(LlmCallRecordModel).filter_by(thread_id=thread_id).all()
        return {
            "prompt_tokens": sum(m.prompt_tokens for m in models),
            "completion_tokens": sum(m.completion_tokens for m in models),
            "estimated_cost_usd": sum(m.estimated_cost_usd for m in models),
        }

    def _to_entity(self, model: LlmCallRecordModel) -> LlmCallRecord:
        return LlmCallRecord(
            call_id=model.call_id,
            correlation_id=model.correlation_id,
            thread_id=model.thread_id,
            agent_name=model.agent_name,
            provider=model.provider,
            model=model.model,
            prompt_tokens=model.prompt_tokens,
            completion_tokens=model.completion_tokens,
            estimated_cost_usd=model.estimated_cost_usd,
            created_at=model.created_at,
        )
