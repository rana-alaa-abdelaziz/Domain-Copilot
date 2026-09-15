import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.human_review_service import HumanReviewService
from backend.infrastructure.api.review_router import router as review_router
from backend.infrastructure.db.repositories.review_task_repository import (
    SqlAlchemyReviewTaskRepository,
)
from backend.infrastructure.orchestration.copilot_graph import create_copilot_graph

# Import your actual agent instances here:
# from backend.application.agents.standards_mapper import StandardsMapper
# from backend.application.agents.module_outline_generator import ModuleOutlineGenerator
# from backend.application.agents.assessment_generator import AssessmentGenerator

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Connect to PostgreSQL checkpointer
    db_url = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/domain_copilot")
    psycopg_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
    
    checkpointer = PostgresSaver.from_conn_string(psycopg_url)
    checkpointer.setup()

    # 2. Instantiate your agents (replace with your actual initialization logic)
    engine = create_engine(db_url)
    SessionLocal = sessionmaker(bind=engine)
    review_task_repository = SqlAlchemyReviewTaskRepository(session=SessionLocal())

    standards_mapper = StandardsMapper(...) # pass required LLM/vector store
    outline_generator = ModuleOutlineGenerator(...)
    assessment_generator = AssessmentGenerator(...)

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
    
    yield
    
    # Cleanup on shutdown if needed

app = FastAPI(title="Domain Copilot API", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

# Register the review router
app.include_router(review_router)