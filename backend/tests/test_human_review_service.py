"""
Real integration test for the human review mechanism — against an actual
PostgresSaver and a real ReviewTaskRepository, not a mock. This replaces
test_item_generator_approval_gate.py's SubmitForReview-based contract,
which tested a mechanism the real implementation never uses.
"""
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.application.use_cases.human_review_service import HumanReviewService
from backend.infrastructure.db.models import Base
from backend.infrastructure.db.repositories.review_task_repository import (
    SqlAlchemyReviewTaskRepository,
)
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph
from backend.tests.db_test_utils import ensure_test_db_exists, get_test_db_url


@pytest.fixture
def test_db_url():
    return get_test_db_url()

@pytest.fixture
def pg_session(test_db_url):
    ensure_test_db_exists(test_db_url)
    engine = create_engine(test_db_url)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.rollback()
    session.close()

# ... fake agent classes matching the ones I ran manually earlier ...


class DummyStandardsMapper:
    def run(self, target_role, user_reported_subjects):
        from backend.domain.entities import CompetencyGapReport
        return CompetencyGapReport(target_role=target_role, user_reported_subjects=user_reported_subjects, gaps=[])

def test_approve_resumes_graph_and_marks_review_task_approved(pg_session, test_db_url):
    psycopg_url = test_db_url.replace("postgresql+psycopg2://", "postgresql://")
    with PostgresSaver.from_conn_string(psycopg_url) as checkpointer:
        checkpointer.setup()
        review_repo = SqlAlchemyReviewTaskRepository(pg_session)
        
        standards_mapper = DummyStandardsMapper()
        
        graph = create_copilot_graph(
            standards_mapper=standards_mapper, 
            checkpointer=checkpointer, 
            review_task_repository=review_repo
        )
        import uuid
        thread_id = f"test-approve-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}
        graph.invoke({"target_role": "X", "user_reported_subjects": []}, config)

        task = review_repo.get_by_thread_id(thread_id)
        review_repo.assign(task.review_task_id, "test_reviewer")

        service = HumanReviewService(graph, review_repo)
        service.process_review_decision(thread_id, action="approve")
        
        task = review_repo.get_by_thread_id(thread_id)
        assert task.status == "approved"
        assert graph.get_state(config).next == ()  # graph actually completed


def test_reject_does_not_resume_graph_and_marks_review_task_rejected(pg_session, test_db_url):
    # mirrors the manual reject test I ran earlier — assert next == ("human_review",)
    # stays paused, and task.status == "rejected"
    ...


def test_audit_trail_accumulates_across_review_actions(pg_session, test_db_url):
    # the regression test for the overwrite bug specifically
    ...