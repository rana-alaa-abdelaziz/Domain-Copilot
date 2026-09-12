"""
Local LlmProvider implementation using Ollama. Chosen over a separate
sentence-transformers embedding library specifically so completions and
embeddings run on one local service (`ollama serve`) rather than two —
matches the provider-abstraction ADR's fallback-chain design.

Requires `ollama pull llama3` and `ollama pull nomic-embed-text` locally.
"""
from collections.abc import Iterator

import ollama

from backend.domain.ports import LlmProvider

# nomic-embed-text is natively 768-dim — this is why OpenAIAdapter forces
# its own embeddings down to 768 via the `dimensions` param, so the two
# adapters are interchangeable behind one pgvector column width.
_EMBEDDING_MODEL = "nomic-embed-text"
_CHAT_MODEL = "llama3"


class OllamaAdapter(LlmProvider):
    def __init__(self, base_url: str):
        self._client = ollama.Client(host=base_url)

    def complete(self, prompt: str, **kwargs) -> str:
        response = self._client.chat(
            model=kwargs.pop("model", _CHAT_MODEL),
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]

    def stream(self, prompt: str, **kwargs) -> Iterator[str]:
        stream = self._client.chat(
            model=kwargs.pop("model", _CHAT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            stream=True,
        )
        for chunk in stream:
            content = chunk["message"]["content"]
            if content:
                yield content

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        response = self._client.chat(
            model=kwargs.pop("model", _CHAT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
        )
        tool_calls = response["message"].get("tool_calls") or []
        if not tool_calls:
            return {"tool": None, "arguments": {}}
        call = tool_calls[0]
        return {"tool": call["function"]["name"], "arguments": call["function"]["arguments"]}

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings(model=_EMBEDDING_MODEL, prompt=text)
        return response["embedding"]
