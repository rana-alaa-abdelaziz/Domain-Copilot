"""
Domain error hierarchy. Raised by domain/application code, caught and
translated to HTTP responses at the infrastructure/api boundary.
"""


class DomainError(Exception):
    """Base class for all domain-level errors."""


class InsufficientEvidenceError(DomainError):
    """Raised when a decision (e.g. gap assignment) lacks enough evidence to proceed."""

class PublicationBlockedError(DomainError):
    """Raised when an attempt is made to publish an item whose ReviewTask
    is not in an approved state."""
