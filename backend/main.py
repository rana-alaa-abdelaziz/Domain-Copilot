import asyncio
import os
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
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
from backend.infrastructure.config import (
    get_instrumented_llm_provider,
)
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
    
        llm_provider = get_instrumented_llm_provider(session=session)
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

from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.infrastructure.api.correlation_middleware import CorrelationIdMiddleware

app = FastAPI(title="Domain Copilot API", lifespan=lifespan)
app.add_middleware(CorrelationIdMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "").split(",") if os.environ.get("ALLOWED_ORIGINS") else [],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response

from backend.infrastructure.api.rate_limiter import limiter

# Note: we need to set app.state.limiter before we include routers
# but we can do it right here since app is created
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/ready")
def ready(request: Request):
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    
    status_code = 200
    details = {"database": "ok", "llm": "ok"}
    
    # Check Database
    try:
        session = request.app.state.db_session
        session.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        details["database"] = f"failed: {e}"
        status_code = 503

    # Check LLM Provider
    try:
        llm = request.app.state.llm_provider
        # Since the provider is wrapped in AccountingProvider, we can access the underlying provider if needed
        # Or just do a cheap reachability check
        provider_name = llm.__class__.__name__
        if "AccountingProvider" in provider_name:
            actual_provider = llm._provider
        else:
            actual_provider = llm
            
        if "OpenAIAdapter" in actual_provider.__class__.__name__:
            # For OpenAI, check if API key is configured
            if not actual_provider._client.api_key:
                raise ValueError("OpenAI API key missing")
        elif "OllamaAdapter" in actual_provider.__class__.__name__:
            # For Ollama, hit its base URL / api/tags or simply let's check its client base url
            import httpx
            # A cheap ping to the base url
            try:
                # ollama base url is in actual_provider._client._client.base_url
                res = httpx.get(f"{actual_provider._client._client.base_url}/api/tags", timeout=2.0)
                res.raise_for_status()
            except Exception as httpe:  # noqa: BLE001
                raise ValueError(f"Ollama not reachable: {httpe}")
    except Exception as e:  # noqa: BLE001
        details["llm"] = f"failed: {e}"
        status_code = 503

    if status_code != 200:
        return JSONResponse(content=details, status_code=status_code)
    
    return details

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