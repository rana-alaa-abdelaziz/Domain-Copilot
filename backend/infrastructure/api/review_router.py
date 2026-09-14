"""
FastAPI router for managing the Human-in-the-Loop review queue.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.application.use_cases.human_review_service import HumanReviewService

router = APIRouter(prefix="/api/reviews", tags=["Human Review Queue"])


class ReviewDecisionRequest(BaseModel):
    action: str = Field(
        ..., description="Explicit action: 'approve', 'reject', or 'edit_with_comment'"
    )
    instructor_comment: str | None = Field(
        None, description="Optional feedback or commentary from the instructor"
    )
    edited_artifacts: dict[str, Any] | None = Field(
        None, description="Optional modified reports if editing during review"
    )


def get_review_service(request: Request) -> HumanReviewService:
    """Dependency provider that pulls the review service from FastAPI app state."""
    if hasattr(request.app.state, "review_service") and request.app.state.review_service:
        return request.app.state.review_service
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Review service dependency is not bound to application state.",
    )


@router.get("/{thread_id}/pending", status_code=status.HTTP_200_OK)
def get_pending_review(
    thread_id: str, service: HumanReviewService = Depends(get_review_service)  # noqa: B008
):
    
    """Fetches paused review artifacts and state for a specific thread."""
    try:
        result = service.get_pending_review(thread_id)
        if result["status"] == "not_pending":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No pending human review found for thread '{thread_id}'.",
            )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch pending review: {exc}",
        ) from exc


@router.post("/{thread_id}/decision", status_code=status.HTTP_200_OK)
def submit_review_decision(
    thread_id: str,
    payload: ReviewDecisionRequest,
    service: HumanReviewService = Depends(get_review_service),  # noqa: B008
):
    
    """
    Submits a lead instructor decision ('approve', 'reject', 'edit_with_comment')
    with full audit logging and resumes workflow execution.
    """
    try:
        response = service.process_review_decision(
            thread_id=thread_id,
            action=payload.action,
            instructor_comment=payload.instructor_comment,
            edited_artifacts=payload.edited_artifacts,
        )
        return response
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        ) from val_err
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process review decision: {exc}",
        ) from exc