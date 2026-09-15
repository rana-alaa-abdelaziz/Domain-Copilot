import threading
import time

from backend.domain.errors.orchestration_errors import ClientCancelledError
from backend.infrastructure.orchestration.copilot_graph import (
    _run_with_retry,
    _run_with_timeout,
)

# Note: We don't test the actual network disconnect here (that's e2e), 
# but we test the orchestration's reaction to a cancel_event being set 
# and how the generator behaves when cancelled.

def test_cancellation_closes_stream_and_avoids_retry():
    # 1. Setup a fake cancel_event and mock stream
    cancel_event = threading.Event()
    
    close_called = False
    
    def slow_stream():
        nonlocal close_called
        try:
            for i in range(10):
                if cancel_event.is_set():
                    # In our adapters, we call stream.close() and break
                    # Here we simulate that adapter logic wrapping the raw stream
                    close_called = True
                    break
                time.sleep(0.1)
                yield f"chunk_{i}"
        except GeneratorExit:
            close_called = True
            raise
            
    def fake_adapter_complete():
        # This mimics the new LlmProvider.complete logic
        chunks = list(slow_stream())
            
        if cancel_event.is_set():
            raise ClientCancelledError()
            
        return "".join(chunks)

    # We need to simulate the _run_with_timeout passing the event
    def fake_call():
        return fake_adapter_complete()

    # Track how many times fn is called to ensure no retries happen
    call_count = 0
    def tracked_call():
        nonlocal call_count
        call_count += 1
        return _run_with_timeout(fake_call, 5, cancel_event)
        
    # 2. Start the work in a thread so we can cancel it mid-flight
    # actually, since _run_with_timeout uses ThreadPoolExecutor, 
    # the fake_call is already running in a thread. 
    # But _run_with_retry blocks. So we run _run_with_retry in a thread.
    result_container = {}
    exc_container = {}
    
    def worker():
        try:
            result_container["res"] = _run_with_retry(tracked_call)
        except Exception as e:  # noqa: BLE001
            exc_container["exc"] = e
            
    t = threading.Thread(target=worker)
    t.start()
    
    # Let it start
    time.sleep(0.2)
    
    # 3. Simulate client disconnect
    cancel_event.set()
    
    # 4. Wait for worker to finish
    t.join(timeout=2.0)
    
    # 5. Assertions
    # Ensure it didn't hang
    assert not t.is_alive(), "Worker thread hung instead of aborting"
    
    # Ensure ClientCancelledError was raised
    exc = exc_container.get("exc")
    assert isinstance(exc, ClientCancelledError), f"Expected ClientCancelledError, got {type(exc)}"
    
    # Ensure close logic was triggered
    assert close_called, "stream.close() was not triggered by the adapter"
    
    # Ensure it did NOT retry
    assert call_count == 1, f"Expected 1 call (no retries), got {call_count} calls"
