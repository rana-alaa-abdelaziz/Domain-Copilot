from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.domain.entities.user import Role, User
from backend.infrastructure.auth.dependencies import get_db
from backend.infrastructure.auth.jwt_handler import create_access_token
from backend.main import app

client = TestClient(app)

# Mock DB session so get_db doesn't fail accessing app.state.db_session
mock_session = MagicMock()

# Mock the user repo behavior by creating mock users
def mock_get_by_email(email):
    if email == "instructor@example.com":
        return User(user_id="1", email=email, hashed_password="x", role=Role.INSTRUCTOR)
    elif email == "lead@example.com":
        return User(user_id="2", email=email, hashed_password="x", role=Role.LEAD_INSTRUCTOR)
    return None

mock_session.query.return_value.filter.return_value.first.side_effect = lambda: MagicMock(
    user_id="1", email="instructor@example.com", hashed_password="x", role="instructor"
) # Simple mock, actually it's better to just mock the UserRepository, but it's instantiated inside get_current_user!
# Let's override the session to one that can be used by SqlAlchemyUserRepository.
# Or better, override get_db to return a session that SqlAlchemyUserRepository can use.
# But SqlAlchemyUserRepository uses session.query(UserModel).filter(...).first()
# Let's just mock it.
mock_query = MagicMock()
mock_filter = MagicMock()
mock_first = MagicMock()
mock_session.query.return_value = mock_query
mock_query.filter.return_value = mock_filter

def side_effect_first():
    # We can't easily get the email from the filter call, so we'll just return a UserModel
    # based on whatever role we need. Actually, if we just test auth_and_roles, we can override
    # get_current_user instead! But we want to test get_current_user!
    pass

from backend.infrastructure.api.review_router import (
    get_review_service,
    get_review_task_repository,
)

# A simpler way is just to connect to the DB using lifespan
# but that requires Postgres running.
# Let's override get_db to return a mock session
app.dependency_overrides[get_db] = lambda: mock_session
app.dependency_overrides[get_review_service] = lambda: MagicMock()
app.dependency_overrides[get_review_task_repository] = lambda: MagicMock()

def test_unauthenticated_access_blocked():
    response = client.get("/api/reviews/pending")
    assert response.status_code == 401
    
    response = client.post("/api/reviews/thread-123/decision", json={"action": "approve"})
    assert response.status_code == 401

def test_instructor_can_access_pending_but_not_decision():
    # We must mock the DB response to return the instructor user
    mock_model = MagicMock(user_id="1", email="instructor@example.com", hashed_password="x", role="instructor")
    mock_filter.first.return_value = mock_model
    
    instructor_token = create_access_token(data={"sub": "instructor@example.com", "role": Role.INSTRUCTOR.value})
    headers = {"Authorization": f"Bearer {instructor_token}"}
    
    # Can access pending
    # NOTE: Since we only mocked get_db, the route handler for pending might fail with 500
    # because it also needs HumanReviewService. So we just check it's NOT 401 or 403.
    response = client.get("/api/reviews/pending", headers=headers)
    assert response.status_code not in [401, 403]
    
    # Try accessing decision (requires lead_instructor)
    response = client.post(
        "/api/reviews/thread-123/decision", 
        headers=headers,
        json={"action": "approve"}
    )
    assert response.status_code == 403  # Forbidden

def test_lead_instructor_can_access_decision():
    # Mock the DB response to return the lead user
    mock_model = MagicMock(user_id="2", email="lead@example.com", hashed_password="x", role="lead_instructor")
    mock_filter.first.return_value = mock_model
    
    lead_token = create_access_token(data={"sub": "lead@example.com", "role": Role.LEAD_INSTRUCTOR.value})
    headers = {"Authorization": f"Bearer {lead_token}"}
    
    response = client.post(
        "/api/reviews/thread-123/decision", 
        headers=headers,
        json={"action": "approve"}
    )
    
    assert response.status_code not in [401, 403]
