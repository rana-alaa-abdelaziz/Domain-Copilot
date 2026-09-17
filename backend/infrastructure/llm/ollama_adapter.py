"""
Local LlmProvider implementation using Ollama. Chosen over a separate
sentence-transformers embedding library specifically so completions and
embeddings run on one local service (`ollama serve`) rather than two —
matches the provider-abstraction ADR's fallback-chain design.

Requires `ollama pull llama3` and `ollama pull nomic-embed-text` locally.
"""

import logging
import threading
from collections.abc import Iterator
from contextvars import ContextVar

import ollama

from backend.domain.errors.orchestration_errors import ClientCancelledError
from backend.domain.ports import LlmProvider

logger = logging.getLogger(__name__)

# nomic-embed-text is natively 768-dim — this is why OpenAIAdapter forces
# its own embeddings down to 768 via the `dimensions` param, so the two
# adapters are interchangeable behind one pgvector column width.
_EMBEDDING_MODEL = "nomic-embed-text"
_CHAT_MODEL = "llama3"


class OllamaAdapter(LlmProvider):
    def __init__(self, base_url: str):
        self._client = ollama.Client(host=base_url)
        self._last_usage: ContextVar[dict | None] = ContextVar("ollama_last_usage", default=None)

    def get_last_usage(self) -> dict | None:
        return self._last_usage.get()

    def complete(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> str:
        chunks = list(self.stream(prompt, cancel_event=cancel_event, **kwargs))
            
        if cancel_event and cancel_event.is_set():
            raise ClientCancelledError()
            
        return "".join(chunks)

    def stream(self, prompt: str, cancel_event: threading.Event | None = None, **kwargs) -> Iterator[str]:
        model = kwargs.pop("model", _CHAT_MODEL)
        
        chat_kwargs = {}
        options = {}
        
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if options:
            chat_kwargs["options"] = options
            
        if "response_format" in kwargs and kwargs["response_format"].get("type") == "json_object":
            chat_kwargs["format"] = "json"
            
        stream = self._client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            **chat_kwargs
        )
        for chunk in stream:
            if cancel_event and cancel_event.is_set():
                stream.close()
                break
                
            # FR-9 cost accounting on final chunk
            if "eval_count" in chunk and chunk["eval_count"] > 0:
                logger.info(f"Ollama usage: {chunk.get('prompt_eval_count', 0)} prompt, {chunk.get('eval_count', 0)} completion")
                self._last_usage.set({
                    "prompt_tokens": chunk.get("prompt_eval_count", 0),
                    "completion_tokens": chunk.get("eval_count", 0),
                    "model": model,
                })

            content = chunk["message"]["content"]
            if content:
                yield content

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        model = kwargs.pop("model", _CHAT_MODEL)
        response = self._client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            tools=tools,
        )
        
        if "eval_count" in response and response["eval_count"] > 0:
            self._last_usage.set({
                "prompt_tokens": response.get("prompt_eval_count", 0),
                "completion_tokens": response.get("eval_count", 0),
                "model": model,
            })
            
        tool_calls = response["message"].get("tool_calls") or []
        if not tool_calls:
            return {"tool": None, "arguments": {}}
        call = tool_calls[0]
        return {
            "tool": call["function"]["name"],
            "arguments": call["function"]["arguments"],
        }

    def embed(self, text: str) -> list[float]:
        response = self._client.embeddings(model=_EMBEDDING_MODEL, prompt=text)
        return response["embedding"]
