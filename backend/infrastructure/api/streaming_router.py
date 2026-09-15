"""
FastAPI router for FR-6 Real-time streaming and client-side cancellation.
"""
import asyncio
import json
import queue
import threading
import uuid

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/stream", tags=["Streaming & Realtime"])


async def _watch_disconnect(request: Request, cancel_event: threading.Event):
    """Polls for client disconnection concurrently to set the cancel event immediately."""
    while True:
        if await request.is_disconnected():
            cancel_event.set()
            break
        await asyncio.sleep(0.5)


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
    cancel_event = threading.Event()
    config = {"configurable": {"thread_id": thread_id, "cancel_event": cancel_event}}
    
    # Initialize the workflow state
    state = {
        "target_role": target_role,
        "user_reported_subjects": user_reported_subjects,
    }

    # Start the concurrent disconnection watcher
    watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))

    async def event_generator():
        try:
            # Yield initial connection confirmation
            yield {
                "event": "connected",
                "data": json.dumps({"thread_id": thread_id, "message": "Stream connected. Starting workflow."})
            }

            stream_iter = graph.astream(state, config, stream_mode="updates")
            pending_task = None

            while True:
                if cancel_event.is_set():
                    break
                
                if pending_task is None:
                    pending_task = asyncio.create_task(anext(stream_iter))
                
                done, pending = await asyncio.wait([pending_task], timeout=15.0)
                
                if not done:
                    # Timeout reached, send keep-alive ping
                    yield {
                        "event": "ping",
                        "data": json.dumps({"message": "keep-alive"})
                    }
                    continue
                
                try:
                    event_payload = pending_task.result()
                    pending_task = None
                except StopAsyncIteration:
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

            if not cancel_event.is_set():
                yield {
                    "event": "paused_for_review",
                    "data": json.dumps({"status": "awaiting_approval", "thread_id": thread_id, "message": "Workflow paused. Please review in the Approval Gate."})
                }

        except asyncio.CancelledError:
            # Server-side work safely aborted upon client disconnection
            cancel_event.set()
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
        finally:
            watcher.cancel()

    return EventSourceResponse(event_generator())


@router.get("/ask")
async def stream_ask(
    request: Request,
    query: str,
    target_role: str = Query(default="")
):
    """
    Streams a grounded answer token-by-token (FR-6 token-level streaming).
    Uses HybridRetrieveUseCase to fetch citations, then streams the LlmProvider.
    """
    retrieve_use_case = request.app.state.retrieve_use_case
    llm_provider = request.app.state.llm_provider
    cancel_event = threading.Event()
    
    # Start the concurrent disconnection watcher
    watcher = asyncio.create_task(_watch_disconnect(request, cancel_event))
    
    # Run the retrieval (fast, synchronous in thread)
    try:
        retrieval_result = await asyncio.to_thread(
            retrieve_use_case.execute, query, top_k=3, doc_category=target_role or None
        )
    except Exception:
        watcher.cancel()
        # Fallback to plain JSON response for errors before SSE starts
        raise
        
    citations_text = "\n\n".join([f"[{i+1}] {c.content}" for i, c in enumerate(retrieval_result.citations)])
    prompt = f"Answer the user query based ONLY on the following citations.\n\nCitations:\n{citations_text}\n\nQuery: {query}"
    
    q = queue.Queue()
    
    def llm_worker():
        try:
            for chunk in llm_provider.stream(prompt, cancel_event=cancel_event):
                q.put(chunk)
            q.put(None)  # EOF marker
        except Exception as e:  # noqa: BLE001
            q.put(e)

    async def event_generator():
        # Start background thread for sync stream
        worker_thread = threading.Thread(target=llm_worker)
        worker_thread.start()
        
        try:
            yield {
                "data": json.dumps({"type": "message", "text": "Stream connected. Generating answer."})
            }
            
            # Yield citations
            cits = [{"document_id": c.doc_id, "score": c.fused_score} for c in retrieval_result.citations]
            yield {
                "data": json.dumps({"type": "citations", "citations": cits})
            }
            
            while True:
                if cancel_event.is_set():
                    break
                    
                try:
                    # Non-blocking get with short sleep allows async loop to breathe
                    # and the watcher task to run.
                    chunk = await asyncio.to_thread(q.get, timeout=0.1)
                except queue.Empty:
                    continue
                    
                if chunk is None:
                    break
                    
                if isinstance(chunk, Exception):
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": str(chunk)})
                    }
                    break
                    
                yield {
                    "data": json.dumps({"type": "token", "text": chunk})
                }
                
            if not cancel_event.is_set():
                # Signal completion
                yield {
                    "event": "done",
                    "data": json.dumps({"status": "completed"})
                }
                
        except asyncio.CancelledError:
            cancel_event.set()
            print("Client disconnected during /ask streaming.")
            raise
        finally:
            watcher.cancel()
            
    return EventSourceResponse(event_generator())