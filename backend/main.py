import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.human_review_service import HumanReviewService
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.infrastructure.api.review_router import router as review_router
from backend.infrastructure.api.streaming_router import router as streaming_router
from backend.infrastructure.config import get_llm_provider
from backend.infrastructure.db.repositories.review_task_repository import (
    SqlAlchemyReviewTaskRepository,
)
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect to PostgreSQL checkpointer
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot")
    psycopg_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    
    async with AsyncPostgresSaver.from_conn_string(psycopg_url) as checkpointer:
        await checkpointer.setup()
    
        # 2. Instantiate your agents (replace with your actual initialization logic)
        engine = create_engine(db_url)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        
        review_task_repository = SqlAlchemyReviewTaskRepository(session=session)
    
        llm_provider = get_llm_provider()
        vector_store = PgVectorStore(session=session)
        keyword_search = PgKeywordSearch(session=session)
        
        retrieve_use_case = HybridRetrieveUseCase(
            llm_provider=llm_provider,
            vector_store=vector_store,
            keyword_search=keyword_search
        )
    
        standards_mapper = StandardsMapper(
            retrieve_use_case=retrieve_use_case,
            llm_provider=llm_provider
        )
        outline_generator = ModuleOutlineGenerator(
            retrieve_use_case=retrieve_use_case,
            llm_provider=llm_provider
        )
        assessment_generator = AssessmentGenerator(
            retrieve_use_case=retrieve_use_case,
            llm_provider=llm_provider
        )
    
        # 3. Create compiled graph with checkpointer and breakpoint
        graph = create_copilot_graph(
            standards_mapper=standards_mapper,
            outline_generator=outline_generator,
            assessment_generator=assessment_generator,
            checkpointer=checkpointer,
            review_task_repository=review_task_repository
        )
    
        # 4. Bind HumanReviewService to FastAPI app state
        app.state.review_service = HumanReviewService(graph=graph, review_task_repository=review_task_repository)
        app.state.review_task_repository = review_task_repository
        app.state.retrieve_use_case = retrieve_use_case
        app.state.llm_provider = llm_provider
        
        yield
    
    # Cleanup on shutdown if needed

app = FastAPI(title="Domain Copilot API", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

# Register the review router
app.include_router(review_router)
app.include_router(streaming_router)

# Mount the frontend static directory for testing
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "static"))
app.mount("/static", StaticFiles(directory=static_dir), name="static")