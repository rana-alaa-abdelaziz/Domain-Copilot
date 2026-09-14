"""
Verification of PostgreSQL state persistence and session recovery.

Critical design point: Phase 1 and Phase 2 use SEPARATE PostgresSaver
and graph instances, with Phase 1's checkpointer fully closed before
Phase 2 begins. This is what actually proves recovery "after a server
restart" — invoking and immediately reading state from the SAME open
connection (the original version of this test) does not rule out
reading from an in-memory cache rather than genuinely deserializing
from Postgres.
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
    reason="Ollama is not running",
)
def test_postgres_persistence_survives_a_simulated_restart():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot",
    )
    engine = create_engine(db_url)
    psycopg_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    thread_config = {"configurable": {"thread_id": "audit-session-backend-dev-001"}}
    initial_state = {
        "target_role": "Junior Backend Developer",
        "user_reported_subjects": ["REST API Design", "Git Version Control"],
        "competency_gap_report": None,
        "module_outline_report": None,
        "assessment_report": None,
        "step_count": 0,
    }

    def _build_agents(session):
        vector_store = PgVectorStore(session)
        keyword_search = PgKeywordSearch(session)
        llm_provider = OllamaAdapter(base_url=ollama_url)
        retrieve_uc = HybridRetrieveUseCase(
            llm_provider=llm_provider, vector_store=vector_store, keyword_search=keyword_search
        )
        return (
            StandardsMapper(retrieve_use_case=retrieve_uc, llm_provider=llm_provider),
            ModuleOutlineGenerator(retrieve_use_case=retrieve_uc, llm_provider=llm_provider),
            AssessmentGenerator(retrieve_use_case=retrieve_uc, llm_provider=llm_provider),
        )

    print("=== Phase 1: run and save, then fully close the connection ===")
    with Session(engine) as session_1:
        standards_mapper, outline_generator, assessment_generator = _build_agents(session_1)
        with PostgresSaver.from_conn_string(psycopg_url) as checkpointer_1:
            checkpointer_1.setup()
            app_1 = create_copilot_graph(
                standards_mapper=standards_mapper,
                outline_generator=outline_generator,
                assessment_generator=assessment_generator,
                checkpointer=checkpointer_1,
            )
            app_1.invoke(initial_state, thread_config)
    # checkpointer_1 and session_1 are now both fully closed — nothing
    # from Phase 1 is still alive in this process for Phase 2 to
    # accidentally read from in-memory.

    print("=== Phase 2: brand new connection, brand new graph — simulated restart ===")
    with Session(engine) as session_2:
        standards_mapper_2, outline_generator_2, assessment_generator_2 = _build_agents(session_2)
        with PostgresSaver.from_conn_string(psycopg_url) as checkpointer_2:
            app_2 = create_copilot_graph(
                standards_mapper=standards_mapper_2,
                outline_generator=outline_generator_2,
                assessment_generator=assessment_generator_2,
                checkpointer=checkpointer_2,
            )
            restored_state = app_2.get_state(thread_config)

            gap_report = restored_state.values.get("competency_gap_report")
            assert gap_report is not None, "Failed to restore competency gap report after simulated restart"

            # Explicitly verify the restored object is still a real,
            # working CompetencyGapReport — not just something that
            # didn't crash. This is the check the msgpack warning made
            # worth being skeptical about.
            assert hasattr(gap_report, "gaps"), (
                f"Restored competency_gap_report lost its type — got {type(gap_report)} "
                f"instead of CompetencyGapReport. This is exactly the failure mode the "
                f"'deserializing unregistered type' msgpack warning was flagging."
            )
            assert len(gap_report.gaps) > 0, "Expected evaluated gaps in restored checkpoint"

            print(f"\n>>> Restored {len(gap_report.gaps)} gaps after simulated restart. "
                  f"Type preserved: {type(gap_report).__name__} <<<")
            print(">>> POSTGRESQL STATE PERSISTENCE CHECK PASSED SUCCESSFULLY! <<<")