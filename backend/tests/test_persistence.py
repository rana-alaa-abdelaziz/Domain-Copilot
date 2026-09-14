"""
Permanent verification script for PostgreSQL state persistence and session recovery.
"""
import os
import urllib.error
import urllib.request

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import (
    ModuleOutlineGenerator,
)
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore


def is_ollama_running(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=1.0)
        return True
    except urllib.error.URLError:
        return False

@pytest.mark.skipif(
    not is_ollama_running(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
    reason="Ollama is not running"
)
def test_postgres_persistence():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot",
    )
    engine = create_engine(db_url)
    psycopg_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    with Session(engine) as session:
        print("=== PostgreSQL State Persistence & Auditability Verification ===")

        vector_store = PgVectorStore(session)
        keyword_search = PgKeywordSearch(session)
        llm_provider = OllamaAdapter(base_url=ollama_url)

        retrieve_uc = HybridRetrieveUseCase(
            llm_provider=llm_provider,
            vector_store=vector_store,
            keyword_search=keyword_search,
        )

        standards_mapper = StandardsMapper(
            retrieve_use_case=retrieve_uc,
            llm_provider=llm_provider,
        )
        outline_generator = ModuleOutlineGenerator(
            retrieve_use_case=retrieve_uc,
            llm_provider=llm_provider,
        )
        assessment_generator = AssessmentGenerator(
            retrieve_use_case=retrieve_uc,
            llm_provider=llm_provider,
        )

        with PostgresSaver.from_conn_string(psycopg_url) as checkpointer:
            checkpointer.setup()

            app = create_copilot_graph(
                standards_mapper=standards_mapper,
                outline_generator=outline_generator,
                assessment_generator=assessment_generator,
                checkpointer=checkpointer,
            )

            thread_config = {
                "configurable": {"thread_id": "audit-session-backend-dev-001"}
            }

            initial_state = {
                "target_role": "Junior Backend Developer",
                "user_reported_subjects": [
                    "REST API Design",
                    "Git Version Control",
                ],
                "competency_gap_report": None,
                "module_outline_report": None,
                "assessment_report": None,
            }

            app.invoke(initial_state, thread_config)
            restored_state = app.get_state(thread_config)

            assert restored_state.values["competency_gap_report"] is not None, (
                "Failed to restore competency gap report from database checkpoint"
            )
            assert len(restored_state.values["competency_gap_report"].gaps) > 0, (
                "Expected evaluated gaps in restored checkpoint"
            )

            print("\n>>> POSTGRESQL STATE PERSISTENCE CHECK PASSED SUCCESSFULLY! <<<")