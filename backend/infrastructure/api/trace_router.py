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
