"""
Stub/fake LlmProvider adapter for local dev and tests, before real
provider adapters (OpenAIAdapter, OllamaAdapter) are wired in.
"""

import threading
from collections.abc import Iterator

from backend.domain.errors.orchestration_errors import ClientCancelledError
from backend.domain.ports import LlmProvider


class StubLlmAdapter(LlmProvider):
    def get_last_usage(self) -> dict | None:
        return {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "model": "stub"
        }

    def complete(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> str:
        if cancel_event and cancel_event.is_set():
            raise ClientCancelledError()
        return "Stub response"

    def stream(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> Iterator[str]:
        if cancel_event and cancel_event.is_set():
            return
        yield "Stub "
        yield "response"

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        return {"tool": None, "arguments": {}}

    def embed(self, text: str) -> list[float]:
        return [0.0] * 768
