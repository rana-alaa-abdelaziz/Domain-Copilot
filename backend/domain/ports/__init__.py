"""
Ports (interfaces) for the domain layer.

LlmProvider: single interface covering completion, streaming, tool-calling,
and embeddings. Concrete adapters (OpenAI, Ollama, stub/fake) live in
infrastructure/llm and implement this interface — domain and application
code depend only on this abstraction, never on a specific SDK.

VectorStore: interface for similarity search / upsert, implemented in
infrastructure/vectorstore.
"""

from abc import ABC, abstractmethod


class LlmProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, **kwargs) -> str: ...

    @abstractmethod
    def stream(self, prompt: str, **kwargs): ...

    @abstractmethod
    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict: ...

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class VectorStore(ABC):
    @abstractmethod
    def upsert(self, ids: list[str], vectors: list[list[float]], metadata: list[dict]) -> None: ...

    @abstractmethod
    def query(self, vector: list[float], top_k: int = 5) -> list[dict]: ...