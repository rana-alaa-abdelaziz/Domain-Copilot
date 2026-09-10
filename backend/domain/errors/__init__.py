"""
Domain error hierarchy. Raised by domain/application code, caught and
translated to HTTP responses at the infrastructure/api boundary.
"""


class DomainError(Exception):
    """Base class for all domain-level errors."""


class InsufficientEvidenceError(DomainError):
    """Raised when a decision (e.g. gap assignment) lacks enough evidence to proceed."""