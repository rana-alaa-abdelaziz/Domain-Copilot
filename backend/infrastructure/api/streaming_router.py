"""
FastAPI router for FR-6 Real-time streaming and client-side cancellation.
"""
import asyncio
import json
import uuid

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/stream", tags=["Streaming & Realtime"])


@router.get("/workflow")
async def stream_workflow_progress(
    request: Request, 
    target_role: str,
    user_reported_subjects: list[str] = Query(default=[])  # noqa: B008
):
    """
    Streams live agent progress events using Server-Sent Events (SSE).
    Stops server-side workflow progression immediately if the client disconnects/cancels.
    """
    graph = request.app.state.review_service.graph
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize the workflow state
    state = {
        "target_role": target_role,
        "user_reported_subjects": user_reported_subjects,
    }

    async def event_generator():
        try:
            # Yield initial connection confirmation
            yield {
                "event": "connected",
                "data": json.dumps({"thread_id": thread_id, "message": "Stream connected. Starting workflow."})
            }

            # graph.astream with stream_mode="updates" yields an event each time a node finishes
            async for event_payload in graph.astream(state, config, stream_mode="updates"):
                if await request.is_disconnected():
                    break
                
                # Extract the node name and state update
                for node_name, updates in event_payload.items():
                    if not isinstance(updates, dict):
                        continue
                        
                    # If a node encountered an error, broadcast it
                    if updates.get("error"):
                        yield {
                            "event": "error",
                            "data": json.dumps({"agent": node_name, "error": updates["error"]})
                        }
                    else:
                        yield {
                            "event": "progress",
                            "data": json.dumps({"agent": node_name, "status": "completed"})
                        }

            if not await request.is_disconnected():
                yield {
                    "event": "complete",
                    "data": json.dumps({"status": "completed", "thread_id": thread_id})
                }

        except asyncio.CancelledError:
            # Server-side work safely aborted upon client disconnection
            print(f"Client disconnected. Aborting background generation task for thread {thread_id}.")
            raise
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"Error in stream: {e!r}")
            traceback.print_exc()
            yield {
                "event": "error",
                "data": json.dumps({"error": repr(e)})
            }

    return EventSourceResponse(event_generator())