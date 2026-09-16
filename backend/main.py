import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
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
from backend.infrastructure.api.ingest_router import router as ingest_router
from backend.infrastructure.api.review_router import router as review_router
from backend.infrastructure.api.streaming_router import router as streaming_router
from backend.infrastructure.api.trace_router import router as trace_router
from backend.infrastructure.config import get_llm_provider
from backend.infrastructure.db.repositories.chunk_repository import (
    SqlAlchemyChunkRepository,
)
from backend.infrastructure.db.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
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
        app.state.db_session = session
        
        doc_repo = SqlAlchemyDocumentRepository(session=session)
        chunk_repo = SqlAlchemyChunkRepository(session=session)
        ingest_doc = IngestDocumentUseCase(repository=doc_repo)
        chunk_doc = ChunkDocumentUseCase(chunk_repository=chunk_repo)
        embed_chunks = EmbedChunksUseCase(
            chunk_repository=chunk_repo, 
            document_repository=doc_repo, 
            llm_provider=llm_provider
        )
        app.state.ingest_pipeline = IngestPipelineUseCase(
            ingest_document_use_case=ingest_doc,
            chunk_document_use_case=chunk_doc,
            embed_chunks_use_case=embed_chunks
        )
        
        yield
    
    # Cleanup on shutdown if needed

app = FastAPI(title="Domain Copilot API", lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok"}

from backend.infrastructure.api.auth_router import router as auth_router

# Register the review router
app.include_router(auth_router)
app.include_router(review_router)
app.include_router(streaming_router)
app.include_router(ingest_router)
app.include_router(trace_router)

# Mount the frontend static directory for testing
static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "static"))
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
def read_root():
    return FileResponse(os.path.join(static_dir, "index.html"))