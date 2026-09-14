"""
Permanent verification script for the LangGraph Orchestrator.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.application.agents.standards_mapper import StandardsMapper
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph

db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot")
engine = create_engine(db_url)
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

with Session(engine) as session:
    print("=== LangGraph Orchestrator Verification ===")

    # 1. Initialize infrastructure & use cases
    vector_store = PgVectorStore(session)
    keyword_search = PgKeywordSearch(session)
    llm_provider = OllamaAdapter(base_url=ollama_url)

    retrieve_uc = HybridRetrieveUseCase(
        llm_provider=llm_provider,
        vector_store=vector_store,
        keyword_search=keyword_search,
    )

    # 2. Initialize pure business logic agent
    standards_mapper = StandardsMapper(
        retrieve_use_case=retrieve_uc,
        llm_provider=llm_provider,
    )

    # 3. Compile the LangGraph orchestrator app
    app = create_copilot_graph(standards_mapper)

    # 4. Set initial graph state
    initial_state = {
        "target_role": "Junior Backend Developer",
        "user_reported_subjects": ["REST API Design", "Git Version Control"],
        "competency_gap_report": None
    }

    print("Invoking LangGraph orchestrator state machine...")
    final_state = app.invoke(initial_state)

    report = final_state["competency_gap_report"]
    print(f"\nGraph execution complete!")
    print(f"Target Role: {report.target_role}")
    print(f"Total Competencies Evaluated: {len(report.gaps)}")
    print(f"Covered Competencies: {len(report.covered_competencies)}")
    print(f"Unverified Gaps: {len(report.unverified_competencies)}")

    assert report is not None, "Graph failed to return a competency gap report"
    assert len(report.gaps) > 0, "Expected evaluated gaps in report"

    print("\n>>> LANGGRAPH ORCHESTRATOR CHECK PASSED SUCCESSFULLY! <<<")