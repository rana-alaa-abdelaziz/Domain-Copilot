from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/trace", tags=["Trace"])

@router.get("/{thread_id}")
async def get_trace(request: Request, thread_id: str):
    """
    Retrieve the execution history (trace) of a workflow thread.
    """
    graph = request.app.state.review_service.graph
    config = {"configurable": {"thread_id": thread_id}}
    
    history = []
    # Use aget_state_history for async checkpointer
    async for snapshot in graph.aget_state_history(config):
        history.append({
            "config": snapshot.config,
            "values": snapshot.values,
            "metadata": getattr(snapshot, "metadata", None),
            "next": snapshot.next,
        })
        
    return {"history": history}

@router.get("/{thread_id}/costs")
async def get_trace_costs(request: Request, thread_id: str):
    """
    Retrieve token totals and estimated cost for a workflow run.
    """
    # Create an ad-hoc session because we don't have a repo dependency here directly for llm calls
    # Actually, we can get db_session from app state
    session = request.app.state.db_session
    from backend.infrastructure.db.repositories.llm_call_repository import (
        SqlAlchemyLlmCallRepository,
    )
    repo = SqlAlchemyLlmCallRepository(session)
    totals = repo.get_totals_by_thread_id(thread_id)
    return totals

@router.get("/correlation/{correlation_id}")
async def get_trace_by_correlation(request: Request, correlation_id: str):
    """
    Retrieve all LLM calls made under one correlation ID.
    """
    session = request.app.state.db_session
    from backend.infrastructure.db.repositories.llm_call_repository import (
        SqlAlchemyLlmCallRepository,
    )
    repo = SqlAlchemyLlmCallRepository(session)
    calls = repo.list_by_correlation_id(correlation_id)
    return {"calls": calls}
