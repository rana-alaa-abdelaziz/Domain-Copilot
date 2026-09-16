from dataclasses import dataclass
from datetime import datetime


@dataclass
class LlmCallRecord:
    call_id: str
    correlation_id: str
    thread_id: str | None      # workflow run, when applicable
    agent_name: str | None     # "standards_mapper", etc., when applicable
    provider: str              # "OpenAIAdapter" | "OllamaAdapter" | "StubLlmAdapter"
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    created_at: datetime
