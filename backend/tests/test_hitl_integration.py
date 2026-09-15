"""
End-to-end integration test for the Human-in-the-Loop review workflow and API endpoints.
"""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.infrastructure.api.review_router import router as review_router

# 1. Create a dedicated test app
app = FastAPI()
app.include_router(review_router)

# 2. Define a Mock Review Service simulating LangGraph pause/resume states
class MockHITLWorkflowService:
    def __init__(self):
        # Store mock threads in memory for testing
        self.threads = {
            "thread-pending-123": {
                "status": "pending_review",
                "target_role": "Backend .NET Developer",
                "user_reported_subjects": ["C#", "ASP.NET Core"],
                "competency_gap_report": {"gaps": ["Microservices patterns"]},
                "module_outline_report": {"modules": ["Advanced gRPC"]},
                "assessment_report": {"items": []}
            }
        }

    def get_pending_review(self, thread_id: str):
        if thread_id not in self.threads:
            return {"status": "not_pending"}
        
        thread_data = self.threads[thread_id]
        if thread_data["status"] != "pending_review":
            return {"status": "not_pending"}
            
        return {
            "thread_id": thread_id,
            "status": "pending_review",
            "target_role": thread_data["target_role"],
            "user_reported_subjects": thread_data["user_reported_subjects"],
            "competency_gap_report": thread_data["competency_gap_report"],
            "module_outline_report": thread_data["module_outline_report"],
            "assessment_report": thread_data["assessment_report"],
        }

    def process_review_decision(
        self,
        thread_id: str,
        action: str,
        instructor_comment: str | None = None,
        edited_artifacts: dict | None = None,
        reviewer_id: str = "system_auto_assign",
    ):
        if thread_id not in self.threads:
            raise ValueError(f"Thread '{thread_id}' not found.")
            
        if action not in ["approve", "reject", "edit_with_comment"]:
            raise ValueError(f"Invalid review action '{action}'.")

        # Update mock state
        self.threads[thread_id]["status"] = f"completed_{action}"
        
        return {
            "thread_id": thread_id,
            "status": "completed",
            "review_status": action,
            "audit": {
                "action": action,
                "instructor_comment": instructor_comment,
                "timestamp": "2026-09-15T00:00:00Z"
            },
            "final_state": {
                "target_role": self.threads[thread_id]["target_role"],
                "assessment_items_count": 0,
            }
        }

# Bind mock service to app state
app.state.review_service = MockHITLWorkflowService()
client = TestClient(app)


def test_get_pending_review_success():
    """Verifies that pending review artifacts are correctly fetched for paused threads."""
    response = client.get("/api/reviews/thread-pending-123/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_review"
    assert data["target_role"] == "Backend .NET Developer"
    assert "competency_gap_report" in data


def test_get_pending_review_not_found():
    """Verifies 404 is raised when a thread has no active review pause."""
    response = client.get("/api/reviews/non-existent-thread/pending")
    assert response.status_code == 404


def test_submit_approval_decision():
    """Verifies submitting an 'approve' decision successfully resumes and completes the workflow."""
    payload = {
        "action": "approve",
        "instructor_comment": "Looks solid, approved for generation."
    }
    response = client.post("/api/reviews/thread-pending-123/decision", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["review_status"] == "approve"
    assert data["audit"]["instructor_comment"] == "Looks solid, approved for generation."


def test_submit_invalid_action():
    """Verifies submitting an unaccepted action returns a 400 Bad Request."""
    payload = {
        "action": "unsupported_action",
        "instructor_comment": "Should fail."
    }
    response = client.post("/api/reviews/thread-pending-123/decision", json=payload)
    assert response.status_code == 400