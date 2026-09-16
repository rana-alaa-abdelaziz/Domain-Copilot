"""
Centralized environment configuration and the LlmProvider factory.

Satisfies the provider-abstraction requirement that provider selection is
config-driven, not hardcoded: set LLM_PROVIDER=openai or LLM_PROVIDER=ollama
in .env and get_llm_provider() returns the matching adapter with no code
change required elsewhere.
"""

import os
import secrets
from functools import lru_cache

from backend.domain.ports import LlmProvider


class Settings:
    def __init__(self):
        self.database_url = os.environ.get("DATABASE_URL", "")
        self.llm_provider = os.environ.get("LLM_PROVIDER", "openai").lower()
        self.openai_api_key = os.environ.get("OPENAI_API_KEY", "")
        self.ollama_base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        self.embedding_dim = 768

        env = os.environ.get("APP_ENV", "development")
        raw_secret = os.environ.get("SECRET_KEY")

        if raw_secret:
            if len(raw_secret.encode("utf-8")) < 32:
                raise RuntimeError(
                    "SECRET_KEY is set but shorter than 32 bytes — "
                    "insecure for HS256 per RFC 7518. Generate one with: "
                    "python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            self.secret_key = raw_secret
        elif env == "development":
            # Only acceptable in explicit local dev — generated fresh
            # per process start, not a fixed, repo-visible string, so it
            # can never be relied on across restarts or leaked via git.
            self.secret_key = secrets.token_urlsafe(32)
        else:
            raise RuntimeError(
                f"SECRET_KEY environment variable is required when "
                f"APP_ENV={env!r}. Refusing to start with no secret "
                f"configured outside of development mode."
            )

@lru_cache
def get_settings() -> Settings:
    return Settings()


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


def get_instrumented_llm_provider(session) -> LlmProvider:
    """
    Returns an LlmProvider wrapped with AccountingProvider that writes
    token usage to the database after each call. Requires an active DB session.
    """
    base_provider = get_llm_provider()
    
    from backend.infrastructure.db.repositories.llm_call_repository import (
        SqlAlchemyLlmCallRepository,
    )
    from backend.infrastructure.llm.accounting_provider import AccountingProvider
    
    repository = SqlAlchemyLlmCallRepository(session)
    return AccountingProvider(provider=base_provider, repository=repository)
