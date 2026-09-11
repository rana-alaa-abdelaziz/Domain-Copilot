"""
Explicitly modelled domain errors — never let a raw SDK/DB exception
bubble past the application layer.
"""
from backend.domain.errors import DomainError


class UnsupportedFileTypeError(DomainError):
    """Raised when a file extension has no registered extractor."""


class DocumentExtractionError(DomainError):
    """Raised when extraction fails for a reason not specific to file type
    (corrupt file, unreadable content, etc.)."""
