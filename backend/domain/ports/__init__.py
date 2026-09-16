"""
Ports (interfaces) for the domain layer.

LlmProvider: single interface covering completion, streaming, tool-calling,
and embeddings. Concrete adapters (OpenAI, Ollama, stub/fake) live in
infrastructure/llm and implement this interface — domain and application
code depend only on this abstraction, never on a specific SDK.

VectorStore: interface for similarity search / upsert, implemented in
infrastructure/vectorstore.
"""

import threading
from abc import ABC, abstractmethod

from backend.domain.ports.chunk_repository import ChunkRepository
from backend.domain.ports.document_repository import DocumentRepository
from backend.domain.ports.keyword_search import KeywordSearchPort


class LlmProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, cancel_event: "threading.Event | None" = None, **kwargs) -> str: ...

    @abstractmethod
    def stream(self, prompt: str, cancel_event: "threading.Event | None" = None, **kwargs): ...

    @abstractmethod
    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict: ...

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def get_last_usage(self) -> dict | None:
        """Returns {"prompt_tokens": int, "completion_tokens": int,
        "model": str} for the most recent call on this provider instance,
        or None if the provider doesn't report usage. Called immediately
        after a completion/tool call to record accounting."""
        ...


class VectorStore(ABC):
    @abstractmethod
    def upsert(
        self, ids: list[str], vectors: list[list[float]], metadata: list[dict]
    ) -> None: ...

    @abstractmethod
    def query(
        self, vector: list[float], top_k: int = 5, doc_category: str | None = None
    ) -> list[dict]:
        """doc_category: when provided, restricts results to chunks whose
        parent document has this category. None means unfiltered."""
        ...


__all__ = [
    "ChunkRepository",
    "DocumentRepository",
    "KeywordSearchPort",
    "LlmProvider",
    "VectorStore",
]
