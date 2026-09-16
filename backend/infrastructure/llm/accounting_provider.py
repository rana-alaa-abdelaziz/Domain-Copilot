import logging
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

from backend.domain.entities.llm_call_record import LlmCallRecord
from backend.domain.ports import LlmProvider
from backend.domain.ports.llm_call_repository import LlmCallRepository
from backend.infrastructure.api.correlation_middleware import get_correlation_id
from backend.infrastructure.llm.pricing import estimate_cost

logger = logging.getLogger(__name__)

# To capture thread_id and agent_name without changing agents,
# we might look at the current langgraph context if possible, 
# or use contextvars if they were set.
# For now, we will try to get them from langgraph config if available.
try:
    from langchain_core.runnables.config import var_child_runnable_config
except ImportError:
    var_child_runnable_config = None

class AccountingProvider(LlmProvider):
    """
    Wraps an LlmProvider to record token usage and estimated cost to the database
    after every call.
    """
    def __init__(self, provider: LlmProvider, repository: LlmCallRepository):
        self._provider = provider
        self._repository = repository

    def _get_context_info(self) -> tuple[str | None, str | None]:
        thread_id = None
        agent_name = None
        
        # Try to extract from LangGraph context if available
        if var_child_runnable_config is not None:
            config = var_child_runnable_config.get()
            if config:
                configurable = config.get("configurable", {})
                thread_id = configurable.get("thread_id")
        
        return thread_id, agent_name

    def _record_usage(self):
        usage = self._provider.get_last_usage()
        if not usage:
            return

        thread_id, agent_name = self._get_context_info()
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        model = usage.get("model", "unknown")
        
        cost = estimate_cost(model, prompt_tokens, completion_tokens)
        
        record = LlmCallRecord(
            call_id=str(uuid.uuid4()),
            correlation_id=get_correlation_id(),
            thread_id=thread_id,
            agent_name=agent_name,
            provider=self._provider.__class__.__name__,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=cost,
            created_at=datetime.now(timezone.utc)
        )
        
        try:
            self._repository.save(record)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Failed to save LLM call record: {e}")

    def get_last_usage(self) -> dict | None:
        return self._provider.get_last_usage()

    def complete(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> str:
        try:
            return self._provider.complete(prompt, cancel_event=cancel_event, **kwargs)
        finally:
            self._record_usage()

    def stream(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> Iterator[str]:
        stream = self._provider.stream(prompt, cancel_event=cancel_event, **kwargs)
        try:
            yield from stream
        finally:
            self._record_usage()

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        try:
            return self._provider.call_tool(prompt, tools=tools, **kwargs)
        finally:
            self._record_usage()

    def embed(self, text: str) -> list[float]:
        # Emdeddings are not currently returning usage in the get_last_usage pattern, 
        # but if they did, we would record it here.
        try:
            return self._provider.embed(text)
        finally:
            self._record_usage()
