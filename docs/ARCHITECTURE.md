# Architecture

## API Layer
- **Streaming (SSE)**: The API provides Server-Sent Events for streaming workflows (`/api/stream/workflow`) and token-by-token LLM streams (`/api/stream/ask`).
- **Cancellation**: Implements deep cancellation where a disconnected HTTP request sets a `threading.Event` which halts LangGraph execution and closes underlying LLM socket streams mid-flight.

<!-- TODO -->
