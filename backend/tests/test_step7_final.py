"""
Permanent verification script for Step 7 Final Orchestrator (DevOps Role).
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore

db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot",
)
engine = create_engine(db_url)
ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

if __name__ == '__main__':
    with Session(engine) as session:
        print("=== Step 7 Final Orchestrator Verification (DevOps Role) ===")

        # 1. Initialize infrastructure & use cases
        vector_store = PgVectorStore(session)
        keyword_search = PgKeywordSearch(session)
        llm_provider = OllamaAdapter(base_url=ollama_url)

        retrieve_uc = HybridRetrieveUseCase(
            llm_provider=llm_provider,
            vector_store=vector_store,
            keyword_search=keyword_search,
        )

        # 2. Initialize pure business logic agents
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

        # 3. Compile the LangGraph orchestrator app with all agents
        app = create_copilot_graph(
            standards_mapper, outline_generator, assessment_generator
        )

        # 4. Set initial graph state for DevOps role
        initial_state = {
            "target_role": "DevOps Engineer",
            "user_reported_subjects": ["Docker Containerization", "CI/CD Pipelines"],
            "competency_gap_report": None,
            "module_outline_report": None,
            "assessment_report": None,
        }

        print("Invoking LangGraph orchestrator state machine...")
        final_state = app.invoke(initial_state)

        report = final_state["competency_gap_report"]
        outline_report = final_state["module_outline_report"]
        assessment_report = final_state["assessment_report"]

        print("\nGraph execution complete!")
        print(f"Target Role: {report.target_role}")
        print(f"Total Competencies Evaluated: {len(report.gaps)}")
        print(f"Modules Generated: {len(outline_report.modules) if outline_report else 0}")
        print(
            f"Assessment Items Generated: {len(assessment_report.items) if assessment_report else 0}"
        )

        assert report is not None, "Graph failed to return a competency gap report"
        assert len(report.gaps) > 0, "Expected evaluated gaps in report"

        print("\n>>> STEP 7 FINAL ORCHESTRATOR CHECK PASSED SUCCESSFULLY! <<<")
