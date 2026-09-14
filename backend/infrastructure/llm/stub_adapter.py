"""
Stub/fake LlmProvider adapter for local dev and tests, before real
provider adapters (OpenAIAdapter, OllamaAdapter) are wired in.
"""

from backend.domain.ports import LlmProvider


class StubLlmAdapter(LlmProvider):
    def complete(self, prompt: str, **kwargs) -> str:
        return "stub completion"

    def stream(self, prompt: str, **kwargs):
        yield "stub completion"

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        return {"tool": None, "arguments": {}}

    def embed(self, text: str) -> list[float]:
        return [0.0] * 768
