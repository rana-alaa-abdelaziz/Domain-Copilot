"""
Hosted LlmProvider implementation using the OpenAI SDK. Only this file
(and ollama_adapter.py) may import the provider SDK — domain and
application code depend on the LlmProvider port, never on this module.
"""

from collections.abc import Iterator

from openai import OpenAI

from backend.domain.ports import LlmProvider

# Kept in sync with backend.infrastructure.config.Settings.embedding_dim
# and the pgvector column width in migration 0002 — text-embedding-3-small
# supports dimension reduction via the `dimensions` param specifically so
# this can be forced to match Ollama's nomic-embed-text (768, native).
_EMBEDDING_DIM = 768
_EMBEDDING_MODEL = "text-embedding-3-small"
_CHAT_MODEL = "gpt-4o-mini"


class OpenAIAdapter(LlmProvider):
    def __init__(self, api_key: str):
        self._client = OpenAI(api_key=api_key)

    def complete(self, prompt: str, **kwargs) -> str:
        response = self._client.chat.completions.create(
            model=kwargs.pop("model", _CHAT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def stream(self, prompt: str, **kwargs) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=kwargs.pop("model", _CHAT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            **kwargs,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        response = self._client.chat.completions.create(
            model=kwargs.pop("model", _CHAT_MODEL),
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            **kwargs,
        )
        message = response.choices[0].message
        if not message.tool_calls:
            return {"tool": None, "arguments": {}}
        call = message.tool_calls[0]
        return {"tool": call.function.name, "arguments": call.function.arguments}

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings.create(
            model=_EMBEDDING_MODEL,
            input=text,
            dimensions=_EMBEDDING_DIM,
        )
        return response.data[0].embedding
