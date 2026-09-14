"""Explicitly modelled domain errors — never let a raw SDK/DB exception
bubble past the application layer."""

from backend.domain.errors import DomainError


class UnsupportedFileTypeError(DomainError):
    """Raised when a file extension has no registered extractor."""


class DocumentExtractionError(DomainError):
    """Raised when extraction fails for a reason not specific to file type
    (corrupt file, unreadable content, etc.)."""


class ChunkingError(DomainError):
    """Raised when chunking produces zero chunks despite extracted text."""


class EmbeddingError(DomainError):
    """Raised when the LLM provider fails to produce an embedding for a
    chunk (provider error, rate limit, malformed response)."""


# 7.MaxIterationsExceededError
# 7.AgentTimeoutError
# 8.ApprovalRequiredError (PublicationBlockedError may already cover this — check before adding a duplicate)
