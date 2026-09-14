import os
import sys
from pathlib import Path

# Explicitly add project root to sys.path
root_dir = Path(__file__).resolve().parents[2]
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore

db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot")
engine = create_engine(db_url)
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

with Session(engine) as session:
    print("=== Step 7 Final Orchestrator Verification (DevOps Role) ===")

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

    app = create_copilot_graph(standards_mapper)

    initial_state = {
        "target_role": "DevOps Engineer",
        "user_reported_subjects": ["Docker Containerization", "CI/CD Pipelines"],
        "competency_gap_report": None
    }

    print(f"Target Role: {initial_state['target_role']}")
    print(f"Reported Subjects: {initial_state['user_reported_subjects']}")
    print("Invoking LangGraph orchestrator state machine...")
    
    final_state = app.invoke(initial_state)

    report = final_state["competency_gap_report"]
    print("\nGraph execution complete!")
    print(f"Target Role: {report.target_role}")
    print(f"Total Competencies Evaluated: {len(report.gaps)}")
    print(f"Covered Competencies: {len(report.covered_competencies)}")
    print(f"Unverified Gaps: {len(report.unverified_competencies)}")

    for idx, gap in enumerate(report.gaps, 1):
        print(f"\n[Competency #{idx}] {gap.competency}")
        print(f"  - Severity:            {gap.severity}")
        print(f"  - Coverage Source:     {gap.coverage_source}")
        print(f"  - Matched Subject:     {gap.matched_user_subject}")

    assert report is not None, "Graph failed to return a competency gap report"
    assert len(report.gaps) > 0, "Expected evaluated gaps in report"

    print("\n>>> STEP 7 FINAL ORCHESTRATOR CHECK PASSED SUCCESSFULLY! <<<")
