"""
Pure function domain service to enforce legal state transitions for Review Tasks.
"""

VALID_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"in_review", "escalated"},
    "in_review": {"approved", "rejected", "edited_approved", "escalated", "in_review", "pending"},
    "escalated": {"in_review", "approved", "rejected", "edited_approved", "escalated"},
    "approved": set(),
    "rejected": set(),
    "edited_approved": set(),
}

def can_transition(from_status: str, to_status: str) -> bool:
    """
    Returns True if the transition from `from_status` to `to_status` is allowed.
    Returns False if it is not allowed or if the statuses are unknown.
    Note: transitions to the exact same status are generally allowed or explicitly defined.
    """
    if from_status not in VALID_TRANSITIONS:
        return False
        
    return to_status in VALID_TRANSITIONS[from_status]
