"""
Integration test for the FastAPI Human Review Queue endpoints.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infrastructure.api.review_router import router as review_router

# Create a test app instance for verification
app = FastAPI()
app.include_router(review_router)

# Mock review service to satisfy dependency injection during tests
class MockReviewService:
    def process_review_decision(self, thread_id: str, action: str, instructor_comment=None, edited_artifacts=None, reviewer_id=None):
        if action not in ["approve", "reject", "edit_with_comment"]:
            raise ValueError(f"Invalid review action '{action}'.")
        return {"thread_id": thread_id, "status": "completed"}

app.state.review_service = MockReviewService()

@app.get("/health")
def health():
    return {"status": "ok"}

from backend.domain.entities.user import Role, User
from backend.infrastructure.auth.dependencies import get_current_user


def mock_get_current_user():
    return User(user_id="test_lead", email="lead@example.com", hashed_password="x", role=Role.LEAD_INSTRUCTOR)

app.dependency_overrides[get_current_user] = mock_get_current_user

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_review_decision_invalid_action():
    """Ensures submitting an invalid review action is rejected with 400 Bad Request."""
    payload = {
        "action": "invalid_action_name",
        "instructor_comment": "This should fail validation."
    }
    response = client.post("/api/reviews/test-thread-001/decision", json=payload)
    assert response.status_code == 400

def test_ownership_assignment_advisory_only():
    """
    Confirms that any authenticated lead_instructor can submit a decision,
    demonstrating that assigned_reviewer_id is informational/advisory,
    not a hard access-control boundary.
    """
    payload = {
        "action": "approve",
        "instructor_comment": "LGTM",
        "reviewer_id": "original-assignee-123" # even if they set this, current_user is lead_instructor
    }
    response = client.post("/api/reviews/test-thread-001/decision", json=payload)
    # The mock review service just returns 200 OK because the user is a lead_instructor
    assert response.status_code == 200