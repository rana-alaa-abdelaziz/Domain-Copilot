from backend.domain.services.review_task_transitions import can_transition


def test_can_transition_allowed():
    assert can_transition("pending", "in_review") is True
    assert can_transition("pending", "escalated") is True
    assert can_transition("in_review", "approved") is True
    assert can_transition("in_review", "rejected") is True
    assert can_transition("in_review", "edited_approved") is True
    assert can_transition("escalated", "in_review") is True
    assert can_transition("escalated", "approved") is True
    
    # Self-transitions
    assert can_transition("in_review", "in_review") is True

def test_can_transition_disallowed():
    # Once terminal, cannot transition
    assert can_transition("approved", "pending") is False
    assert can_transition("rejected", "in_review") is False
    assert can_transition("edited_approved", "in_review") is False
    
    # Escalated cannot go back to pending
    assert can_transition("escalated", "pending") is False
    
    # Pending cannot jump to approved directly without review
    assert can_transition("pending", "approved") is False

def test_can_transition_unknown_status():
    assert can_transition("unknown_status", "pending") is False
    assert can_transition("pending", "unknown_status") is False
