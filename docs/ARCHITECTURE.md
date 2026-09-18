# Architecture

## API & Streaming Layer (FR-6)
- **Streaming (SSE)**: The API provides Server-Sent Events for streaming workflows (`/api/stream/workflow`) and token-by-token LLM streams (`/api/stream/ask`).
- **Cancellation**: Implements deep cancellation where a disconnected HTTP request sets a `threading.Event` which halts LangGraph execution and closes underlying LLM socket streams mid-flight.

## Workflow Orchestration
- **LangGraph**: Used as the core state machine orchestration engine to manage the AI Copilot pipeline (Standards Mapping → Outline Generation → Assessment Generation → Human Review).
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

---

## Diagrams

### C4 Level 1 — System Context

> The outermost view: Domain Copilot as a single system, showing all people and external systems that interact with it.

```mermaid
C4Context
    title System Context — Domain Copilot

    Person(instructor, "Instructor", "Submits a target role and subject list; views the generated curriculum and chat answers")
    Person(lead_instructor, "Lead Instructor", "Claims and reviews curriculum drafts from the approval queue; approves, edits, or rejects")

    System(domain_copilot, "Domain Copilot", "Generates standards-aligned curriculum (gap analysis, module outline, assessment items) using RAG and agentic LLM pipeline with human-in-the-loop review")

    System_Ext(openai, "OpenAI API", "Hosted LLM provider: text generation and embeddings (text-embedding-3-small / GPT-4o-mini)")
    System_Ext(ollama, "Ollama", "Local LLM provider: text generation and embeddings (nomic-embed-text / llama3); all processing stays on-premise")
    System_Ext(corpus, "Corpus Documents", "PDF/TXT competency frameworks and curriculum standards uploaded by instructors and stored in Postgres")

    Rel(instructor, domain_copilot, "Submits role + subjects; reads SSE stream; chats with corpus", "HTTPS / SSE")
    Rel(lead_instructor, domain_copilot, "Claims review tasks; approves / edits / rejects drafts", "HTTPS")
    Rel(domain_copilot, openai, "Sends system prompt + retrieved chunk snippets + query; receives generated text / embeddings", "HTTPS")
    Rel(domain_copilot, ollama, "Sends system prompt + retrieved chunk snippets + query; receives generated text / embeddings", "HTTP local")
    Rel(instructor, corpus, "Uploads documents via ingest endpoint", "HTTPS multipart")
    Rel(corpus, domain_copilot, "Chunked, embedded, and stored in Postgres", "internal")
```

---

### C4 Level 2 — Container

> The real moving pieces: each deployable unit, how they communicate, and which external systems each one talks to.

```mermaid
C4Container
    title Container Diagram — Domain Copilot

    Person(instructor, "Instructor")
    Person(lead_instructor, "Lead Instructor")

    System_Boundary(dc, "Domain Copilot") {
        Container(frontend, "Frontend Static Site", "HTML / Vanilla JS / CSS", "Single-page app served by FastAPI. Renders the workflow UI, SSE stream display, review queue, and chat interface")
        Container(backend, "FastAPI Backend", "Python 3.12 / FastAPI / Uvicorn", "REST + SSE API. Hosts all routers, orchestrates use cases, manages app state and dependency injection at startup")
        Container(langgraph, "LangGraph Orchestrator", "Python / LangGraph StateGraph", "Compiled agentic graph: standards_mapper to module_outline_generator to assessment_generator to interrupt_before human_review to publish_curriculum")
        Container(postgres, "PostgreSQL + pgvector", "Postgres 16 + pgvector extension", "Primary relational store: documents, chunks, users, review_task, published_curriculum, llm_call_record. AND vector store: chunk.embedding 768-dim cosine index. AND LangGraph checkpoint store")
        ContainerDb(checkpoint_tables, "LangGraph Checkpoint Tables", "Postgres tables", "checkpoints, checkpoint_blobs, checkpoint_writes — managed by langgraph-checkpoint-postgres")
    }

    System_Ext(openai, "OpenAI API")
    System_Ext(ollama, "Ollama local")

    Rel(instructor, frontend, "Visits in browser", "HTTPS")
    Rel(lead_instructor, frontend, "Visits in browser", "HTTPS")
    Rel(frontend, backend, "API calls + SSE stream", "HTTPS / SSE")
    Rel(backend, langgraph, "Invokes graph.stream() / graph.update_state()", "In-process Python call")
    Rel(langgraph, postgres, "Reads/writes checkpoints; repositories read/write domain tables", "SQLAlchemy / psycopg2")
    Rel(backend, postgres, "Reads/writes domain tables via SQLAlchemy repositories", "SQLAlchemy / psycopg2")
    Rel(backend, openai, "OpenAIAdapter: chat completions + embeddings", "HTTPS")
    Rel(backend, ollama, "OllamaAdapter: chat completions + embeddings", "HTTP local")
    Rel(postgres, checkpoint_tables, "Same Postgres instance; separate schema managed by LangGraph", "internal")
```

---

### C4 Level 3 — Component (FastAPI Backend)

> Zoomed into the backend container — domain, application, and infrastructure component groups, the agents, ports, and repositories.

```mermaid
C4Component
    title Component Diagram — FastAPI Backend

    Container_Boundary(backend, "FastAPI Backend") {

        Component_Boundary(domain_layer, "domain/") {
            Component(entities, "Entities", "Pure Pydantic dataclasses", "Document, Chunk, CompetencyGapReport, ModuleOutlineReport, AssessmentItemReport, ReviewTask, User, LlmCallRecord")
            Component(ports, "Ports interfaces", "Python ABCs", "LlmProvider, VectorStore, KeywordSearch, DocumentRepository, ChunkRepository, ReviewTaskRepository, PublishedCurriculumRepository, WorkflowGraph")
            Component(domain_services, "Domain Services", "Pure Python", "retrieval_fusion RRF, review_priority SLA/priority compute, pii_detection")
        }

        Component_Boundary(application_layer, "application/") {
            Component(standards_mapper, "StandardsMapper Agent", "Python", "RAG + LLM: maps target role + subjects to competency gaps via hybrid retrieval")
            Component(outline_agent, "ModuleOutlineGenerator Agent", "Python", "Generates structured module outline from gap report via RAG + LLM")
            Component(assessment_agent, "AssessmentGenerator Agent", "Python", "Generates MCQ/scenario assessment items per gap subject via RAG + LLM")
            Component(use_cases, "Use Cases", "Python", "IngestDocument, ChunkDocument, EmbedChunks, HybridRetrieve, IngestPipeline, HumanReviewService")
        }

        Component_Boundary(infrastructure_layer, "infrastructure/") {
            Component(api_routers, "API Routers", "FastAPI routers", "streaming_router SSE, review_router, ingest_router, auth_router, trace_router")
            Component(copilot_graph, "CopilotGraph", "LangGraph StateGraph", "Compiled graph with interrupt_before human_review; FR-5 resilience wrappers: timeout, retry, iteration cap, cancellation")
            Component(openai_adapter, "OpenAIAdapter", "openai SDK", "Implements LlmProvider: GPT-4o-mini chat + text-embedding-3-small at 768 dims")
            Component(ollama_adapter, "OllamaAdapter", "ollama SDK", "Implements LlmProvider: local llama3 chat + nomic-embed-text at 768 dims")
            Component(accounting_provider, "AccountingProvider", "Decorator", "Wraps any LlmProvider; intercepts calls to log tokens + cost to llm_call_record table")
            Component(pgvector_store, "PgVectorStore", "SQLAlchemy + pgvector", "Implements VectorStore: cosine similarity search with 0.3 similarity floor")
            Component(pg_keyword_search, "PgKeywordSearch", "SQLAlchemy tsvector", "Implements KeywordSearch: Postgres full-text search via websearch_to_tsquery")
            Component(db_repositories, "SQLAlchemy Repositories", "SQLAlchemy ORM", "SqlAlchemyDocumentRepository, SqlAlchemyChunkRepository, SqlAlchemyReviewTaskRepository, SqlAlchemyPublishedCurriculumRepository")
            Component(auth, "Auth / RBAC", "FastAPI dependencies", "JWT bearer token validation, require_role() dependency, bcrypt password hashing, rate limiting via slowapi")
        }
    }

    Rel(api_routers, use_cases, "Invokes")
    Rel(api_routers, copilot_graph, "Streams / resumes via HumanReviewService")
    Rel(use_cases, ports, "Calls through port interfaces")
    Rel(standards_mapper, ports, "Calls LlmProvider + VectorStore + KeywordSearch via ports")
    Rel(outline_agent, ports, "Calls LlmProvider + VectorStore + KeywordSearch via ports")
    Rel(assessment_agent, ports, "Calls LlmProvider + VectorStore + KeywordSearch via ports")
    Rel(copilot_graph, standards_mapper, "Executes as graph node")
    Rel(copilot_graph, outline_agent, "Executes as graph node")
    Rel(copilot_graph, assessment_agent, "Executes as graph node")
    Rel(openai_adapter, ports, "Implements LlmProvider")
    Rel(ollama_adapter, ports, "Implements LlmProvider")
    Rel(accounting_provider, openai_adapter, "Wraps decorator pattern")
    Rel(pgvector_store, ports, "Implements VectorStore")
    Rel(pg_keyword_search, ports, "Implements KeywordSearch")
    Rel(db_repositories, ports, "Implements Repository ports")
    Rel(auth, api_routers, "Guards endpoints via FastAPI dependencies")
```

---

### Sequence Diagram — Full Agentic Workflow

> The complete request lifecycle: from instructor submission through the three agents, the `interrupt_before` approval-gate pause and resume, and SSE streaming back to the client. Includes the non-happy path (rejection).

```mermaid
sequenceDiagram
    autonumber
    actor Instructor
    actor LeadInstructor as Lead Instructor
    participant Frontend
    participant StreamingRouter as streaming_router<br/>(FastAPI SSE)
    participant Graph as CopilotGraph<br/>(LangGraph)
    participant SM as StandardsMapper<br/>Agent
    participant OG as ModuleOutlineGenerator<br/>Agent
    participant AG as AssessmentGenerator<br/>Agent
    participant DB as Postgres<br/>(checkpoint + domain tables)
    participant LLM as LLM Provider<br/>(OpenAI / Ollama)

    Note over Instructor,LLM: PHASE 1 - Workflow Submission and Agent Execution

    Instructor->>Frontend: Enter target_role + subjects, click Generate
    Frontend->>StreamingRouter: POST /api/stream/workflow {target_role, subjects} + JWT
    StreamingRouter->>StreamingRouter: Validate JWT, extract user. Create cancel_event threading.Event
    StreamingRouter->>Graph: graph.stream(state, config={thread_id, cancel_event}). Opens SSE response to client

    Note over Graph,DB: graph.stream() starts node execution

    Graph->>DB: Write checkpoint BEFORE standards_mapper
    Graph->>SM: run_standards_mapper(state)
    SM->>LLM: Hybrid retrieve: embed query to pgvector cosine + tsvector FTS. Send system_prompt + retrieved_chunk_snippets to LLM
    LLM-->>SM: Streamed tokens → competency_gap_report JSON
    SM-->>Graph: Return {competency_gap_report}
    Graph->>DB: Write checkpoint AFTER standards_mapper
    Graph-->>StreamingRouter: SSE event: {node: "standards_mapper", data: competency_gap_report}
    StreamingRouter-->>Frontend: data: {"node":"standards_mapper",...}

    Graph->>OG: run_module_outline_generator(state)
    OG->>LLM: Retrieve relevant chunks + generate outline
    LLM-->>OG: module_outline_report JSON
    OG-->>Graph: Return {module_outline_report}
    Graph->>DB: Write checkpoint AFTER module_outline_generator
    Graph-->>StreamingRouter: SSE event: {node: "module_outline_generator", data: module_outline}
    StreamingRouter-->>Frontend: data: {"node":"module_outline_generator",...}

    Graph->>AG: run_assessment_generator(state)
    AG->>LLM: Per-subject loop: retrieve chunks + generate MCQs
    LLM-->>AG: assessment_report JSON
    AG-->>Graph: Return {assessment_report}
    Graph->>DB: Write checkpoint AFTER assessment_generator
    Graph-->>StreamingRouter: SSE event: {node: "assessment_generator", data: assessment_items}
    StreamingRouter-->>Frontend: data: {"node":"assessment_generator",...}

    Graph->>DB: run_create_review_task → INSERT review_task status=PENDING priority=computed
    Graph->>DB: Write checkpoint BEFORE human_review

    Note over Graph,StreamingRouter: interrupt_before=["human_review"] fires — graph PAUSES and suspends

    Graph-->>StreamingRouter: graph.stream() returns: graph is suspended at interrupt
    StreamingRouter-->>Frontend: data: {"node":"__interrupt__","status":"awaiting_review"}
    StreamingRouter-->>Frontend: SSE stream closed cleanly

    Note over LeadInstructor,DB: PHASE 2 - Human Review Pull Model

    LeadInstructor->>Frontend: Navigate to review queue
    Frontend->>StreamingRouter: GET /api/reviews/pending JWT with role=lead_instructor
    StreamingRouter-->>Frontend: [{thread_id, priority, sla_due_at, ...}]

    LeadInstructor->>Frontend: Click Claim on a review task
    Frontend->>StreamingRouter: POST /api/reviews/{thread_id}/assign JWT
    StreamingRouter->>DB: UPDATE review_task SET status=IN_REVIEW assigned_reviewer_id=user_id
    StreamingRouter-->>Frontend: 200 OK

    LeadInstructor->>Frontend: Review generated curriculum, click Approve or Reject

    alt Approved
        Frontend->>StreamingRouter: POST /api/reviews/{thread_id}/decision {decision: "approved"} + JWT role=lead_instructor
        StreamingRouter->>Graph: graph.update_state(config, {review_status: "approved"})
        Graph->>DB: Write updated state to checkpoint
        StreamingRouter->>Graph: graph.stream(None, config) — RESUME from interrupt
        Graph->>Graph: run_human_review → route_after_review → publish_curriculum
        Graph->>DB: INSERT published_curriculum module_outline + assessment_items + approved_by
        Graph->>DB: Write final checkpoint END
        Graph-->>StreamingRouter: stream ends
        StreamingRouter->>DB: UPDATE review_task SET status=APPROVED
        StreamingRouter-->>Frontend: SSE events: {node:"human_review"} then {node:"publish_curriculum"}
    else Rejected
        Frontend->>StreamingRouter: POST /api/reviews/{thread_id}/decision {decision: "rejected"} + JWT
        StreamingRouter->>Graph: graph.update_state(config, {review_status: "rejected"})
        StreamingRouter->>Graph: graph.stream(None, config) — RESUME
        Graph->>Graph: run_human_review → route_after_review → END no publish
        Graph->>DB: Write final checkpoint END
        StreamingRouter->>DB: UPDATE review_task SET status=REJECTED
        StreamingRouter-->>Frontend: SSE event: {node:"human_review", status:"rejected"}
    end

    Note over Instructor,LLM: PHASE 3 - SSE Token Streaming ask endpoint

    Instructor->>Frontend: Type question in chat input
    Frontend->>StreamingRouter: POST /api/stream/ask {question} + JWT
    StreamingRouter->>LLM: Hybrid retrieve relevant chunks → stream chat completion
    LLM-->>StreamingRouter: Token stream delta events
    StreamingRouter-->>Frontend: data: {"token":"..."} per token live
    StreamingRouter-->>Frontend: data: {"citations":[...]}
    StreamingRouter-->>Frontend: data: [DONE]
```

---

### Data-Flow Diagram — Trust Boundaries & LLM Provider Data Exposure

> This diagram is the evidence base for the Data Exfiltration control in [SECURITY.md](./SECURITY.md#data-exfiltration-owasp-llm06).
> It shows exactly what data crosses the trust boundary to an external LLM provider versus what stays inside infrastructure.

```mermaid
flowchart TD
    subgraph INTERNAL ["Internal Infrastructure — Trust Boundary"]
        direction TB
        INSTR["Instructor Input\ntarget_role string + subjects list"]
        UPLOAD["Uploaded Corpus Documents\nraw PDF / TXT bytes"]
        CHUNK["Chunk Table\ncontent text, embedding vector,\nstandard_id, hierarchy_path"]
        PG[("PostgreSQL\nall domain tables,\ncheckpoints, vectors")]
        SYSTEM_PROMPT["System Prompt Templates\nin prompts/ directory\ninstruction-only, no user PII"]
        RETRIEVED["Retrieved Chunk Snippets\ntop-k chunks from hybrid search\ncorpus text only, NOT raw doc bytes"]
        AGENT["Agent / Use Case\nassembles final prompt"]
        RESPONSE["LLM Response\ncompetency_gap_report,\nmodule_outline, assessment_items,\nchat answer"]
        CHAT_HISTORY["chat_message table\nstored in Postgres\nnever sent to LLM"]
    end

    subgraph OPENAI_BOUNDARY ["OpenAI Trust Boundary — data leaves infrastructure"]
        OPENAI_API["OpenAI API\ntext-embedding-3-small\nGPT-4o-mini"]
    end

    subgraph OLLAMA_BOUNDARY ["Ollama Boundary — data stays local, no external egress"]
        OLLAMA_API["Ollama\nnomic-embed-text\nllama3 local process"]
    end

    INSTR -->|"target_role + subjects list\nWARNING: CROSSES BOUNDARY if OpenAI"| AGENT
    UPLOAD -->|"Parsed, chunked, embedded\nat ingestion time"| CHUNK
    CHUNK -->|"Stored"| PG
    PG -->|"top-k chunks text snippets only\nnot raw doc bytes"| RETRIEVED
    SYSTEM_PROMPT --> AGENT
    RETRIEVED --> AGENT

    AGENT -->|"OPENAI PATH: Final prompt =\nsystem_prompt + retrieved_snippets\n+ target_role + subjects\nWARNING: Sent to OpenAI"| OPENAI_API
    AGENT -->|"OLLAMA PATH: Final prompt =\nsystem_prompt + retrieved_snippets\n+ target_role + subjects\nOK: Stays local"| OLLAMA_API

    OPENAI_API -->|"Generated text"| RESPONSE
    OLLAMA_API -->|"Generated text"| RESPONSE
    RESPONSE -->|"Stored as chat_message"| CHAT_HISTORY
    CHAT_HISTORY --> PG

    style INTERNAL fill:#1a2a1a,stroke:#4ade80,color:#e2e8f0
    style OPENAI_BOUNDARY fill:#2a1a1a,stroke:#f87171,color:#e2e8f0
    style OLLAMA_BOUNDARY fill:#1a1a2a,stroke:#60a5fa,color:#e2e8f0
```

**What the LLM provider sees (OpenAI path):**
- ✅ System prompt — instruction text only, no user data
- ⚠️ Retrieved chunk **snippets** from the corpus — corpus text, not raw uploaded bytes
- ⚠️ The instructor's `target_role` string and `subjects` list
- ✅ NOT sent: raw PDF bytes, hashed passwords, JWT tokens, other users' data, chat history, or database credentials

**No PII redaction occurs before sending.** The PII detection service (`domain/services/pii_detection.py`) logs detected PII at ingestion time only — it does not redact before LLM calls. This is a documented limitation in [SECURITY.md](./SECURITY.md#sensitive-data-disclosure).

---

### ER Diagram — Postgres Schema

> Generated directly from [`infrastructure/db/models.py`](../backend/infrastructure/db/models.py). Enum-typed columns are annotated with their valid values. LangGraph checkpoint tables are included for completeness.

```mermaid
erDiagram
    document {
        UUID     doc_id          PK "primary key"
        string   source          "filename or origin reference"
        string   version
        string   hash            UK "SHA-256 idempotency key"
        string   doc_category    "requirement or methodology or reference_curriculum or NULL"
        datetime created_at
        datetime updated_at
    }

    ingestion_status {
        UUID     id              PK
        UUID     doc_id          FK "to document.doc_id UNIQUE"
        enum     status          "pending or processing or ready or failed"
        text     error_message   "NULL unless status=failed"
        datetime updated_at
    }

    chunk {
        UUID     chunk_id        PK
        UUID     doc_id          FK "to document.doc_id"
        text     content
        int      chunk_index     "order within document; UNIQUE with doc_id"
        string   standard_id     "NULL if no standard mapping"
        string   hierarchy_path  "e.g. framework > competency > indicator"
        string   page            "page number or clause ref"
        datetime created_at
        vector   embedding       "768-dim pgvector cosine index; NULL until embedded"
        tsvector search_vector   "COMPUTED to_tsvector english content GIN-indexed"
    }

    users {
        string   user_id         PK
        string   email           UK
        string   hashed_password "bcrypt"
        string   role            "instructor or lead_instructor"
    }

    review_task {
        UUID     review_task_id      PK
        string   thread_id           UK "LangGraph thread_id"
        string   item_id
        string   target_role
        enum     status              "pending or in_review or approved or rejected or edited_approved or escalated"
        enum     priority            "high or medium or low"
        datetime sla_due_at
        string   assigned_reviewer_id "NULL until claimed by a lead_instructor"
        text     comment
        datetime created_at
        datetime updated_at
    }

    published_curriculum {
        UUID     published_id     PK
        string   thread_id        UK "LangGraph thread_id"
        string   target_role
        jsonb    module_outline
        jsonb    assessment_items
        string   approved_by
        datetime published_at
    }

    llm_call_record {
        string   call_id              PK
        string   correlation_id       "request correlation ID; indexed"
        string   thread_id            "LangGraph thread_id; NULL for chat calls; indexed"
        string   agent_name           "standards_mapper or outline_generator or assessment_generator"
        string   provider             "openai or ollama"
        string   model
        int      prompt_tokens
        int      completion_tokens
        float    estimated_cost_usd
        datetime created_at
    }

    chat_message {
        UUID     message_id      PK
        string   user_id         FK "to users.user_id; indexed"
        string   role            "user or assistant"
        text     content
        jsonb    citations       "NULL for user messages; array of citation objects"
        datetime created_at
    }

    langgraph_checkpoints {
        string   thread_id       PK "composite PK"
        string   checkpoint_ns   PK "composite PK"
        string   checkpoint_id   PK "composite PK"
        jsonb    checkpoint       "full serialised graph state"
        jsonb    metadata
    }

    document ||--|| ingestion_status : "has one"
    document ||--o{ chunk : "has many"
    users ||--o{ chat_message : "sends"
    review_task }o--o| users : "assigned_to nullable"
```

---

### Layer-Dependency Diagram

> Proves the dependency direction enforced by [`tests/test_architecture_boundaries.py`](../backend/tests/test_architecture_boundaries.py).
> Arrows show **who depends on whom**. Solid arrows = allowed imports. Dashed arrows = forbidden (mechanically tested).

```mermaid
flowchart TB
    subgraph INFRA ["infrastructure/ — Concrete Adapters"]
        direction TB
        subgraph LLM_INFRA ["LLM Adapters"]
            OA["OpenAIAdapter"]
            OlA["OllamaAdapter"]
            AP["AccountingProvider"]
        end
        subgraph DB_INFRA ["Database"]
            REPOS["SQLAlchemy Repositories"]
            MODELS["ORM Models models.py"]
        end
        subgraph VS_INFRA ["Vector Store"]
            PGV["PgVectorStore"]
            PGKW["PgKeywordSearch"]
        end
        subgraph ORCH_INFRA ["Orchestration"]
            GRAPH["CopilotGraph\nLangGraph StateGraph"]
        end
        subgraph API_INFRA ["API"]
            ROUTERS["FastAPI Routers\nstreaming, review, ingest, auth, trace"]
        end
    end

    subgraph APP ["application/ — Use Cases & Agents"]
        direction TB
        SM2["StandardsMapper"]
        OG2["ModuleOutlineGenerator"]
        AG2["AssessmentGenerator"]
        UC["Use Cases\nIngest, Embed, HybridRetrieve,\nHumanReviewService"]
    end

    subgraph DOMAIN ["domain/ — Entities, Ports & Services"]
        direction TB
        ENT["Entities\nDocument, Chunk, CompetencyGapReport,\nModuleOutlineReport, AssessmentItemReport,\nReviewTask, User, LlmCallRecord"]
        PORTS["Ports ABCs\nLlmProvider, VectorStore,\nKeywordSearch, Repositories,\nWorkflowGraph"]
        DSVC["Domain Services\nretrieval_fusion, review_priority,\npii_detection"]
    end

    subgraph EXT ["External SDKs and Frameworks\nOnly reachable from infrastructure/"]
        direction LR
        OAI["openai SDK"]
        OLL["ollama SDK"]
        SQA["SQLAlchemy\n+ psycopg2"]
        LGR["LangGraph\n+ checkpoint-postgres"]
        FAST["FastAPI\n+ Uvicorn"]
        PGV2["pgvector"]
    end

    INFRA -->|"allowed: infra imports app"| APP
    INFRA -->|"allowed: infra imports domain"| DOMAIN
    APP -->|"allowed: app imports domain"| DOMAIN

    DOMAIN -.->|"FORBIDDEN\nenforced by test"| APP
    DOMAIN -.->|"FORBIDDEN\nenforced by test"| INFRA
    APP -.->|"FORBIDDEN\nenforced by test"| INFRA

    LLM_INFRA --> OAI
    LLM_INFRA --> OLL
    DB_INFRA --> SQA
    VS_INFRA --> SQA
    VS_INFRA --> PGV2
    ORCH_INFRA --> LGR
    API_INFRA --> FAST

    style DOMAIN fill:#14532d,stroke:#4ade80,color:#f0fdf4
    style APP fill:#1e3a5f,stroke:#60a5fa,color:#eff6ff
    style INFRA fill:#3b1f1f,stroke:#f87171,color:#fff1f2
    style EXT fill:#2d2d2d,stroke:#6b7280,color:#d1d5db
```

---

## Architecture Decision Records

The full ADR files live in [`docs/adr/`](./adr/). The decisions are summarised here for cross-referencing with the diagrams above.

### ADR-000 — Architecture Style (Accepted)

**Decision**: Adopt Clean Architecture layering — `domain/` (entities + ports, zero external imports), `application/` (agents + use cases, depends only on `domain.ports`), `infrastructure/` (all concrete adapters). An automated boundary test (`test_architecture_boundaries.py`) mechanically enforces that `domain/` and `application/` never import restricted SDK/framework packages. See the **Layer-Dependency Diagram** above.

**Why**: LLM provider APIs and model names are expected to change. Isolating them in `infrastructure/` means swapping OpenAI → Ollama (or any future provider) touches only one adapter file, never domain logic.

---

### ADR-001 / ADR-006 — Chunking & Hybrid Retrieval (Accepted)

**Decision**: Reciprocal Rank Fusion (RRF, k=60) over two independent retrieval legs:

- **Dense leg**: `pgvector` cosine similarity on `chunk.embedding` (768-dim). Enforces a **0.3 minimum cosine similarity floor** before a chunk is a candidate — added after the first real eval run showed 0% refusal correctness without it (cosine search always returns top-k regardless of actual relevance; see `EVALUATION.md`).
- **Keyword leg**: Postgres full-text search via `tsvector` / `websearch_to_tsquery` on `chunk.search_vector` (computed column, GIN-indexed).
- **Fusion formula**: `score(chunk) = Σ 1/(60 + rank)` summed over whichever result lists the chunk appears in.

**Why not weighted linear combination**: `ts_rank` and cosine similarity are on incomparable scales; rank-based fusion avoids requiring normalisation.

**Rejected**: A mirroring ts_rank threshold for the keyword leg — Postgres FTS already only returns genuine lexical matches (unlike dense search's always-return-top-k), so a threshold adds false-negative risk without fixing the actual remaining failure case (q21-style coincidental single-word matches). Documented as an accepted limitation in `EVALUATION.md`.

---

### ADR-003 / ADR-005 — Vector Store Choice & Embedding Dimensions (Accepted)

**Decision**: `pgvector` as an extension on the same Postgres instance already used for relational data — not a separate dedicated vector database (Qdrant, Pinecone, Chroma). Embedding dimension standardised at **768** across both providers:
- `OpenAIAdapter`: calls `text-embedding-3-small` with `dimensions=768` (model supports native dimension reduction via this parameter).
- `OllamaAdapter`: uses `nomic-embed-text`, which is natively 768-dim.

This means switching `LLM_PROVIDER` in config never requires a schema migration — both adapters produce vectors that fit the same column.

**Why not a dedicated vector DB**: Running a second database service adds real operational complexity (another container, another connection string, another failure mode) for a corpus of ~500 chunks — well within what pgvector's `ivfflat` index (lists=100) handles comfortably.

**Known constraint**: If a future embedding model doesn't support reduction to 768, this decision needs revisiting. The `ivfflat` index is calibrated for low-thousands of rows; a switch to HNSW would be needed at an order-of-magnitude larger corpus.

---

### ADR-002 — Orchestration Pattern (T5's Central Decision — Accepted)

**Decision**: LangGraph `StateGraph` as the orchestration engine for the three-agent pipeline, compiled with `interrupt_before=["human_review"]` and a `PostgresSaver` checkpointer. See the **Sequence Diagram** above for the exact pause/resume mechanism.

**Why LangGraph over manual orchestration / Celery / a plain pipeline**:
- **Durable pause**: `interrupt_before` causes the graph to checkpoint its full state to Postgres and suspend — the process can restart without losing work. Manual `asyncio` or thread coordination has no native equivalent.
- **Resume semantics**: `graph.update_state()` + `graph.stream(None, config)` is the explicit, tested resume path (exercised in `test_architecture_boundaries.py` and `review_router.py`). The graph does not re-run completed nodes.
- **Audit trail**: `CopilotState.audit_trail` uses `operator.add` so every node appends to a persisted list — the full execution history is in the checkpoint.

**FR-5 resilience controls applied at the graph level** (not inside individual agents):
- `MAX_ITERATIONS = 10` iteration cap across all nodes
- Per-step timeouts (`STEP_TIMEOUT_SECONDS = 300`, `ASSESSMENT_TIMEOUT_SECONDS = 1200`) via `ThreadPoolExecutor` (Windows-compatible; no `signal.alarm`)
- `MAX_RETRIES = 2` with exponential backoff (`2^attempt` seconds) for transient LLM failures
- Deep cancellation via `cancel_event` (`threading.Event`) propagated through `RunnableConfig` into every agent, closing the underlying LLM socket stream mid-flight

---

### ADR-004 — Review Task Assignment & Priority (T5 Pull-Model — Accepted)

**Decision**: Human review uses a **pull model** with computed SLA and priority. See the **Sequence Diagram** (Phase 2) above for the full flow.

- On `create_review_task` node execution, a `review_task` row is inserted with `status=PENDING` and no assigned reviewer.
- Priority is computed by `domain/services/review_priority.py` based on the gap report (number of gaps, presence of high-severity standards). Values: `HIGH / MEDIUM / LOW`.
- SLA deadline computed from priority: HIGH → 24 h, MEDIUM → 72 h, LOW → 7 days.
- Lead Instructors see all `PENDING` tasks in the queue and claim one via `POST /api/reviews/{thread_id}/assign` (role-gated by `require_role("lead_instructor")`). This avoids the thundering-herd problem of push-assignment when multiple reviewers are online simultaneously.
- Decision endpoint (`POST /api/reviews/{thread_id}/decision`) calls `graph.update_state()` then immediately streams the resumed graph — the review is synchronous from the API caller's perspective but the graph state is durably checkpointed in Postgres before and after.
