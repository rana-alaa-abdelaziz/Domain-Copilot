# Architecture

## API & Streaming Layer (FR-6)
- **Streaming (SSE)**: The API provides Server-Sent Events for streaming workflows (`/api/stream/workflow`) and token-by-token LLM streams (`/api/stream/ask`).
- **Cancellation**: Implements deep cancellation where a disconnected HTTP request sets a `threading.Event` which halts LangGraph execution and closes underlying LLM socket streams mid-flight.

## Workflow Orchestration
- **LangGraph**: Used as the core state machine orchestration engine to manage the AI Copilot pipeline (Standards Mapping -> Outline Generation -> Assessment Generation -> Human Review).
- **Postgres Checkpointing**: Uses `langgraph-checkpoint-postgres` to durably save the state of the graph, allowing long-running tasks to be paused and resumed seamlessly.

## Human-in-the-Loop Review (Twist T5)
- **Pull Model**: Uses an enterprise review queue where tasks are created as "Unassigned". Lead Instructors manually claim tasks from the pending queue via `POST /api/reviews/{thread_id}/assign`.
- **Role-Based Access Control**: Strict role enforcement (`require_role("lead_instructor")`) is implemented at the FastAPI endpoint boundary for assignment and decision workflows.

## Database & Vector Storage
- **Postgres**: Serves as the primary persistence layer (managed via SQLAlchemy and Alembic) and the vector store (via `pgvector`).
- **Chat Persistence**: Full conversational history and AI citations are safely logged to a dedicated `chat_messages` table to persist sessions across page reloads.

## LLM Adapters & Cost Tracking (FR-9)
- **Adapter Pattern**: The domain logic communicates exclusively through the `LlmProvider` abstract interface. Concrete implementations include `OpenAIAdapter`, `OllamaAdapter`, and `StubLlmAdapter` (for tests).
- **AccountingProvider**: A decorator implementation of `LlmProvider` that intercepts all calls, extracts token usage/costs, and writes them to an `LlmCallRecord` in Postgres asynchronously.
