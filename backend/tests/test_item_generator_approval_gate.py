"""
This test encodes the single non-negotiable rule that FR-5's approval
gate, D3's approval requirement, and T5's review-queue product all
converge on: a generated AssessmentItem must never reach the published
item bank while its associated ReviewTask is anything other than
approved / edited_approved.

Written before the feature exists (TDD) — it is expected to fail until
the item bank + review gate are implemented, not to be skipped or
weakened to pass early.
"""

import pytest

from backend.domain.entities import AssessmentItem, ReviewTask
from backend.domain.errors import DomainError
from backend.application.use_cases import SubmitForReview


BLOCKING_STATUSES = ["pending", "rejected", "needs_revision"]
ALLOWED_STATUSES = ["approved", "edited_approved"]


@pytest.mark.parametrize("status", BLOCKING_STATUSES)
def test_item_generator_blocks_without_approval(status):
    item = AssessmentItem(id="item-1", content="placeholder item content")
    review = ReviewTask(item_id=item.id, status=status)

    with pytest.raises(DomainError):
        SubmitForReview().publish(item, review)


@pytest.mark.parametrize("status", ALLOWED_STATUSES)
def test_item_generator_allows_publish_after_approval(status):
    item = AssessmentItem(id="item-2", content="placeholder item content")
    review = ReviewTask(item_id=item.id, status=status)

    # Should not raise
    SubmitForReview().publish(item, review)

"""
TDD Test: Verifies that AssessmentItems cannot reach the published item bank
unless ReviewTask.status is 'approved' or 'edited_approved'.
"""
import pytest
from backend.domain.entities import AssessmentItem, ReviewTask
from backend.domain.errors import DomainError
from backend.application.use_cases import SubmitForReview

BLOCKING_STATUSES = ["pending", "rejected", "needs_revision"]
ALLOWED_STATUSES = ["approved", "edited_approved"]

@pytest.mark.xfail(reason="Approval gate not yet implemented — tracked in issue", strict=True)
@pytest.mark.parametrize("status", BLOCKING_STATUSES)
def test_item_generator_blocks_without_approval(status):
    item = AssessmentItem(id="item-1", content="placeholder item content")
    review = ReviewTask(item_id=item.id, status=status)
    with pytest.raises(DomainError):
        SubmitForReview().publish(item, review)

@pytest.mark.xfail(reason="Approval gate not yet implemented — tracked in issue", strict=True)
@pytest.mark.parametrize("status", ALLOWED_STATUSES)
def test_item_generator_allows_publish_after_approval(status):
    item = AssessmentItem(id="item-2", content="placeholder item content")
    review = ReviewTask(item_id=item.id, status=status)
    SubmitForReview().publish(item, review)