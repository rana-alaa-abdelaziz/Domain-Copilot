"""
Centralized environment configuration and the LlmProvider factory.

Satisfies the provider-abstraction requirement that provider selection is
config-driven, not hardcoded: set LLM_PROVIDER=openai or LLM_PROVIDER=ollama
in .env and get_llm_provider() returns the matching adapter with no code
change required elsewhere.
"""

import os
from dataclasses import dataclass
from functools import lru_cache

from backend.domain.ports import LlmProvider


@dataclass(frozen=True)
class Settings:
    database_url: str
    llm_provider: str
    openai_api_key: str
    ollama_base_url: str
    embedding_dim: int = 768
    secret_key: str = "insecure_dev_secret"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ.get("DATABASE_URL", ""),
        llm_provider=os.environ.get("LLM_PROVIDER", "openai").lower(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        secret_key=os.environ.get("SECRET_KEY") or "insecure_dev_secret",
    )


def get_llm_provider(settings: Settings | None = None) -> LlmProvider:
    """
    Fallback chain: if LLM_PROVIDER=openai but no API key is configured,
    fall back to the local Ollama adapter rather than failing outright —
    this is the documented fallback behavior the provider-abstraction ADR
    describes for the free-tier-runs-out scenario.
    """
    settings = settings or get_settings()

    if settings.llm_provider == "ollama":
        from backend.infrastructure.llm.ollama_adapter import OllamaAdapter

        return OllamaAdapter(base_url=settings.ollama_base_url)

    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            from backend.infrastructure.llm.ollama_adapter import OllamaAdapter

            return OllamaAdapter(base_url=settings.ollama_base_url)
        from backend.infrastructure.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(api_key=settings.openai_api_key)

    raise ValueError(
        f"Unknown LLM_PROVIDER={settings.llm_provider!r}; expected 'openai' or 'ollama'"
    )
