"""
Hosted LlmProvider implementation using the OpenAI SDK. Only this file
(and ollama_adapter.py) may import the provider SDK — domain and
application code depend on the LlmProvider port, never on this module.
"""

import logging
import threading
from collections.abc import Iterator
from contextvars import ContextVar

from openai import OpenAI

from backend.domain.errors.orchestration_errors import ClientCancelledError
from backend.domain.ports import LlmProvider

logger = logging.getLogger(__name__)

# Kept in sync with backend.infrastructure.config.Settings.embedding_dim
# and the pgvector column width in migration 0002 — text-embedding-3-small
# supports dimension reduction via the `dimensions` param specifically so
# this can be forced to match Ollama's nomic-embed-text (768, native).
_EMBEDDING_DIM = 768
_EMBEDDING_MODEL = "text-embedding-3-small"
_CHAT_MODEL = "gpt-4o-mini"


class OpenAIAdapter(LlmProvider):
    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        chat_model: str = _CHAT_MODEL,
        embedding_model: str = _EMBEDDING_MODEL,
        embedding_provider: LlmProvider | None = None,
    ):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._chat_model = chat_model
        self._embedding_model = embedding_model
        self._embedding_provider = embedding_provider
        self._last_usage: ContextVar[dict | None] = ContextVar("openai_last_usage", default=None)

    def get_last_usage(self) -> dict | None:
        return self._last_usage.get()

    def complete(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> str:
        chunks = list(self.stream(prompt, cancel_event=cancel_event, **kwargs))
        
        if cancel_event and cancel_event.is_set():
            raise ClientCancelledError()
            
        return "".join(chunks)

    def stream(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> Iterator[str]:
        model = kwargs.pop("model", self._chat_model)
        stream = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            stream_options={"include_usage": True},
            **kwargs,
        )
        for chunk in stream:
            if cancel_event and cancel_event.is_set():
                stream.close()
                break
                
            if chunk.usage:
                # FR-9 cost accounting
                logger.info(f"OpenAI usage: {chunk.usage.prompt_tokens} prompt, {chunk.usage.completion_tokens} completion")
                self._last_usage.set({
                    "prompt_tokens": chunk.usage.prompt_tokens,
                    "completion_tokens": chunk.usage.completion_tokens,
                    "model": model,
                })
                
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        model = kwargs.pop("model", self._chat_model)
        response = self._client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
            **kwargs,
        )
        
        if response.usage:
            self._last_usage.set({
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "model": model,
            })
            
        message = response.choices[0].message
        if not message.tool_calls:
            return {"tool": None, "arguments": {}}
        call = message.tool_calls[0]
        return {"tool": call.function.name, "arguments": call.function.arguments}

    def embed(self, text: str) -> list[float]:
        if self._embedding_provider is not None:
            return self._embedding_provider.embed(text)

        response = self._client.embeddings.create(
            model=self._embedding_model,
            input=text,
            dimensions=_EMBEDDING_DIM,
        )
        return response.data[0].embedding
