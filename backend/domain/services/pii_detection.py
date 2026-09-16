import re

_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_PATTERN = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")

def detect_pii(text: str) -> list[str]:
    """Returns a list of PII category names found, e.g. ['email', 'phone'].
    Deliberately conservative (regex, not ML) — false negatives are
    expected and documented as a known limitation, not hidden."""
    found = []
    if _EMAIL_PATTERN.search(text):
        found.append("email")
    if _PHONE_PATTERN.search(text):
        found.append("phone")
    return found
