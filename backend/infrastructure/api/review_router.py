"""
FastAPI router for managing the Human-in-the-Loop review queue.
"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from backend.application.use_cases.human_review_service import HumanReviewService
from backend.domain.ports.review_task_repository import ReviewTaskRepository

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
    reviewer_id: str | None = Field(
        None, description="Optional identity of the reviewer making the decision"
    )


def get_review_service(request: Request) -> HumanReviewService:
    """Dependency provider that pulls the review service from FastAPI app state."""
    if hasattr(request.app.state, "review_service") and request.app.state.review_service:
        return request.app.state.review_service
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Review service dependency is not bound to application state.",
    )


def get_review_task_repository(request: Request) -> ReviewTaskRepository:
    """Dependency provider that pulls the review task repository from FastAPI app state."""
    if hasattr(request.app.state, "review_task_repository") and request.app.state.review_task_repository:
        return request.app.state.review_task_repository
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Review task repository dependency is not bound to application state.",
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
            reviewer_id=payload.reviewer_id or "system_auto_assign",
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

@router.get("/pending", status_code=status.HTTP_200_OK)
def list_pending_reviews(
    reviewer_id: str | None = None,
    review_task_repo: ReviewTaskRepository = Depends(get_review_task_repository),  # noqa: B008
):
    """The endpoint that was missing entirely — lets a reviewer discover
    what's waiting for them without already knowing a thread_id."""
    tasks = review_task_repo.list_pending(assigned_reviewer_id=reviewer_id)
    return {"count": len(tasks), "tasks": tasks}


class AssignRequest(BaseModel):
    reviewer_id: str


@router.post("/{thread_id}/assign", status_code=status.HTTP_200_OK)
def assign_review(
    thread_id: str,
    payload: AssignRequest,
    review_task_repo: ReviewTaskRepository = Depends(get_review_task_repository),  # noqa: B008
):
    task = review_task_repo.get_by_thread_id(thread_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"No review task for thread '{thread_id}'")
    review_task_repo.assign(task.review_task_id, payload.reviewer_id)
    return {"thread_id": thread_id, "assigned_reviewer_id": payload.reviewer_id}
    
@router.get("/stats/all", status_code=status.HTTP_200_OK)
def get_reviewer_statistics(
    review_task_repo: ReviewTaskRepository = Depends(get_review_task_repository),  # noqa: B008
):
    """
    Retrieves aggregated reviewer statistics including tasks processed,
    approval rates, and rejection breakdowns per reviewer (T5 requirement).
    """
    try:
        stats = review_task_repo.get_reviewer_stats()
        return {"reviewer_statistics": stats}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch reviewer statistics: {exc}",
        ) from exc