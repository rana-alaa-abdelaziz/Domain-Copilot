"""
Interactive script to run the Domain Copilot graph until the Human Review breakpoint,
inspect the generated reports, and approve or reject the run.
"""
import os
import sys

# Ensure root is in path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from langgraph.checkpoint.postgres import PostgresSaver

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator

# Agent imports
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.human_review_service import HumanReviewService

# Infrastructure adapters & use cases
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph

# Import your repository/vector store adapters here if needed, e.g.:
# from backend.infrastructure.persistence.postgres_vector_store import PostgresVectorStore
# from backend.infrastructure.persistence.postgres_keyword_search import PostgresKeywordSearch


def main():
    print("🚀 Initializing Domain Copilot HITL Workflow Demo...")

    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot")
    psycopg_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    
    with PostgresSaver.from_conn_string(psycopg_url) as checkpointer:
        checkpointer.setup()

        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        llm_provider = OllamaAdapter(base_url=ollama_base_url)

        vector_store = None  # Replace with your PostgresVectorStore
        keyword_search = None  # Replace with your PostgresKeywordSearch

        retrieve_use_case = HybridRetrieveUseCase(
            llm_provider=llm_provider,
            vector_store=vector_store,
            keyword_search=keyword_search
        )

        standards_mapper = StandardsMapper(retrieve_use_case=retrieve_use_case, llm_provider=llm_provider)
        outline_generator = ModuleOutlineGenerator(retrieve_use_case=retrieve_use_case, llm_provider=llm_provider)
        assessment_generator = AssessmentGenerator(retrieve_use_case=retrieve_use_case, llm_provider=llm_provider)

        graph = create_copilot_graph(
            standards_mapper=standards_mapper,
            outline_generator=outline_generator,
            assessment_generator=assessment_generator,
            checkpointer=checkpointer
        )

        review_service = HumanReviewService(compiled_graph=graph)

        thread_id = "demo-thread-001"
        config = {"configurable": {"thread_id": thread_id}}
        
        initial_input = {
            "target_role": "Backend .NET Developer",
            "user_reported_subjects": ["C#", "ASP.NET Core", "SQL Server"]
        }

        print(f"\n▶️ Starting graph execution for role: '{initial_input['target_role']}' (Thread ID: {thread_id})...")
        
        try:
            graph.invoke(initial_input, config)
        except Exception as e:  # noqa: BLE001
            print(f"Graph execution paused or hit breakpoint: {e}")

        pending_review = review_service.get_pending_review(thread_id)
        
        if pending_review["status"] == "pending_review":
            print("\n==============================================")
            print("⏸️  WORKFLOW PAUSED AT HUMAN REVIEW CHECKPOINT")
            print("==============================================")
            print(f"Target Role: {pending_review.get('target_role')}")
            print(f"Competency Gaps: {pending_review.get('competency_gap_report')}")
            print(f"Module Outlines: {pending_review.get('module_outline_report')}")
            print(f"Assessment Items: {pending_review.get('assessment_report')}")
            print("==============================================\n")

            action = input("Enter decision ([a]pprove / [r]eject): ").strip().lower()
            
            if action in ['a', 'approve']:
                print("\n✅ Approving and resuming workflow...")
                result = review_service.process_review_decision(
                    thread_id=thread_id,
                    action="approve",
                    instructor_comment="Approved via interactive CLI demo."
                )
                print("🎉 Workflow Completed Successfully!")
                print(result)
            elif action in ['r', 'reject']:
                print("\n❌ Rejecting workflow...")
                result = review_service.process_review_decision(
                    thread_id=thread_id,
                    action="reject",
                    instructor_comment="Rejected via interactive CLI demo."
                )
                print("🛑 Workflow Terminated.")
                print(result)
            else:
                print("⚠️ Unrecognized choice. Exiting without decision.")
        else:
            print(f"\nℹ️ Workflow status: {pending_review['status']}")

if __name__ == "__main__":
    main()