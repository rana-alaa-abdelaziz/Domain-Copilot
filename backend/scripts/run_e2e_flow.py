"""
End-to-End Test Flow Demo
-------------------------
This script runs the entire FR-1 pipeline, from document ingestion (extract -> clean -> chunk -> embed)
to the copilot graph execution (standards -> outline -> assessment), pausing at the human review gate.

It will:
1. Initialize the PostgreSQL database schema.
2. Provide a dummy file and ingest it using the pipeline.
3. Configure the Copilot Graph with real HybridRetrieveUseCase and Postgres Vector Stores.
4. Run the workflow and pause for human approval.
"""

import logging
import os
import uuid
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.chunk_document import ChunkDocumentUseCase
from backend.application.use_cases.embed_chunks import EmbedChunksUseCase
from backend.application.use_cases.human_review_service import HumanReviewService
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.application.use_cases.ingest_document import IngestDocumentUseCase
from backend.application.use_cases.ingest_pipeline import IngestPipelineUseCase
from backend.infrastructure.db.models import Base
from backend.infrastructure.db.repositories.chunk_repository import (
    SqlAlchemyChunkRepository,
)
from backend.infrastructure.db.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from backend.infrastructure.db.repositories.published_curriculum_repository import (
    SqlAlchemyPublishedCurriculumRepository,
)
from backend.infrastructure.db.repositories.review_task_repository import (
    SqlAlchemyReviewTaskRepository,
)
from backend.infrastructure.llm.ollama_adapter import OllamaAdapter
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore

logging.basicConfig(level=logging.WARNING)

def run_e2e():
    print("🚀 Initializing E2E Flow...")
    
    # 1. Database Setup
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/domain_copilot")
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    print("\n📦 Setting up Repositories and Pipeline...")
    doc_repo = SqlAlchemyDocumentRepository(session)
    chunk_repo = SqlAlchemyChunkRepository(session)
    review_repo = SqlAlchemyReviewTaskRepository(session)
    pub_repo = SqlAlchemyPublishedCurriculumRepository(session)
    
    # Needs to match Ollama running locally
    # If Ollama is not available, you can use StubLlmAdapter for testing
    llm_provider = OllamaAdapter(base_url="http://localhost:11434")
    
    vector_store = PgVectorStore(session)
    keyword_search = PgKeywordSearch(session)
    
    # 2. Ingest Pipeline Setup
    def text_extractor(path: Path) -> list[dict]:
        return [{"page": "Page 1", "text": path.read_text()}]
        
    ingest_doc = IngestDocumentUseCase(
        repository=doc_repo,
        extractors={".txt": text_extractor},
        hash_fn=lambda p: str(hash(p.read_text()))
    )
    chunk_doc = ChunkDocumentUseCase(chunk_repository=chunk_repo)
    embed_chunks = EmbedChunksUseCase(chunk_repository=chunk_repo, document_repository=doc_repo, llm_provider=llm_provider)
    
    ingest_pipeline = IngestPipelineUseCase(ingest_doc, chunk_doc, embed_chunks)
    
    # 3. Create dummy file and Ingest
    print("\n📄 Creating and Ingesting Document...")
    dummy_file = Path("dummy_competency.txt")
    dummy_file.write_text("Backend .NET Developers must know C#, ASP.NET Core, and SQL Server. This is a standard competency requirement.")
    
    try:
        pipeline_result = ingest_pipeline.execute(
            file_path=dummy_file, 
            source="dummy_competency.txt", 
            version="1.0", 
            doc_category="competency"
        )
        print(f"✅ Ingestion successful! Doc ID: {pipeline_result.ingestion.document.doc_id}")
    except Exception as e:  # noqa: BLE001
        print(f"⚠️ Ingestion failed: {e}")
        return
        
    session.commit()

    # 4. Agent and Graph Setup
    print("\n🤖 Initializing Copilot Graph...")
    retrieve_use_case = HybridRetrieveUseCase(
        vector_store=vector_store,
        keyword_search=keyword_search,
        llm_provider=llm_provider
    )
    
    standards_mapper = StandardsMapper(retrieve_use_case, llm_provider)
    outline_generator = ModuleOutlineGenerator(retrieve_use_case, llm_provider)
    assessment_generator = AssessmentGenerator(retrieve_use_case, llm_provider)
    
    with PostgresSaver.from_conn_string(db_url) as checkpointer:
        checkpointer.setup()
        
        graph = create_copilot_graph(
            standards_mapper=standards_mapper,
            outline_generator=outline_generator,
            assessment_generator=assessment_generator,
            checkpointer=checkpointer,
            review_task_repository=review_repo,
            published_curriculum_repository=pub_repo
        )
        
        human_review_service = HumanReviewService(
            graph=graph, 
            review_task_repository=review_repo,
            published_curriculum_repository=pub_repo
        )
        
        # 5. Run Graph Workflow
        print("\n⚙️ Running Copilot Graph for Target Role 'Backend .NET Developer'...")
        thread_id = f"e2e_demo_thread_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = {
            "target_role": "Backend .NET Developer",
            "user_reported_subjects": ["C#", "ASP.NET", "Database"]
        }
        
        print("\n...Streaming graph steps...")
        for event in graph.stream(initial_state, config):
            for k in event:
                print(f"--- Completed Node: {k} ---")
                
        # Check if paused
        current_state = graph.get_state(config)
        if current_state and "human_review" in current_state.next:
            print("\n🛑 Graph execution PAUSED at human_review gate!")
            # Display the generated assessment items for review
            state_values = current_state.values
            assessment_report = state_values.get("assessment_report")
            if assessment_report and assessment_report.items:
                print("\n📋 === GENERATED ASSESSMENT ITEMS FOR REVIEW ===")
                for i, item in enumerate(assessment_report.items, 1):
                    print(f"\n[{i}] {item.question_type.upper()} ({item.difficulty})")
                    print(f"Question: {item.question_text}")
                    if item.options:
                        print(f"Options: {', '.join(item.options)}")
                    if item.correct_answer:
                        print(f"Answer: {item.correct_answer}")
                    if item.rationale:
                        print(f"Rationale: {item.rationale}")
                print("===============================================\n")
            else:
                print("\n⚠️ No assessment items were generated to review.\n")

            task = review_repo.get_by_thread_id(thread_id)
            if task:
                print("Review Task Details:")
                print(f"  - Target Role: {task.target_role}")
                print(f"  - Status: {task.status}")
                print("  - Action Needed: Review the generated assessment plan.")
                
            print("\nPress Enter to APPROVE, type 'reject' to reject, or type 'edit_with_comment'.")
            user_input = input("> ").strip().lower()
            
            if user_input == "reject":
                action = "reject"
                msg = "❌ Rejecting task..."
            elif user_input == "edit_with_comment":
                action = "edit_with_comment"
                msg = "📝 Approving with edits/comments..."
            else:
                action = "approve"
                msg = "✅ Approving task..."
            
            print(msg)
                
            try:
                # E2E demo acts as the reviewer; assign the task to itself first
                review_repo.assign(task.review_task_id, reviewer_id="e2e_demo_user")
                
                # Process decision using HumanReviewService
                comment = "Terminal demo comment" if action == "edit_with_comment" else None
                result = human_review_service.process_review_decision(thread_id, action=action, instructor_comment=comment)
                session.commit()
                
                print(f"\n🎉 E2E Flow Completed Successfully! Final Status: {result['status']}")
                
                final_task = review_repo.get_by_thread_id(thread_id)
                print(f"Final Task Status in DB: {final_task.status}")
                if action == 'approve':
                    print(f"Assessment Items Generated: {len(assessment_report.items) if assessment_report else 0}")
                    
                    # Verify publication
                    if result.get("published"):
                        print(f"🏆 Verification Success: Curriculum was automatically published! (ID: {result.get('published_id')})")
                    else:
                        print("❌ Verification Failure: Curriculum was NOT published!")
                
            except Exception as e:  # noqa: BLE001
                print(f"Error during human review process: {e}")
                
        else:
            print("Graph did not pause for human review as expected.")
            print("Next steps:", current_state.next if current_state else "None")


if __name__ == "__main__":
    run_e2e()
