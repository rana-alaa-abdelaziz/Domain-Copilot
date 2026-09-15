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