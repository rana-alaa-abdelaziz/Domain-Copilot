# ADR-005: Vector Store Choice and Embedding Dimension Standardization

## Status
Accepted

## Context
FR-1/FR-2 require a vector store for dense retrieval. The provider
abstraction (LlmProvider port) requires at least two working embedding
implementations (hosted + local), selected by configuration. These two
requirements interact: different embedding models produce different
vector dimensions, but a pgvector column has one fixed width.

## Decision

**Vector store**: pgvector, as an extension on the same Postgres instance
already used for relational data (Document, Chunk, IngestionStatus
tables) — not a separate dedicated vector database (Qdrant, Pinecone,
Chroma).

**Embedding dimension**: standardized at 768 across both providers:
- OpenAIAdapter calls text-embedding-3-small with `dimensions=768`
  (the model natively supports dimension reduction via this parameter)
- OllamaAdapter uses nomic-embed-text, which is natively 768-dim

This means switching LLM_PROVIDER in config never requires a schema
migration — both adapters produce vectors that fit the same column.

## Alternatives Considered

**Dedicated vector database (Qdrant/Pinecone/Chroma)**: rejected. Running
a second database service adds real operational complexity (another
container, another connection string, another thing that can fail on a
clean-machine `docker compose up`) for a corpus of ~500 chunks — well
within what pgvector's ivfflat index handles comfortably. This is a
deliberate simplicity tradeoff appropriate for a 40-hour solo build, not
a claim that pgvector is universally superior at larger scale.

**Leaving embedding dimensions at each provider's native default**
(OpenAI 1536, Ollama 768): rejected. This would require either a
schema migration on every provider swap, or maintaining two separate
vector columns/tables — both add real complexity to what config-driven
provider switching is supposed to make trivial. Forcing both to 768 via
OpenAI's dimensions parameter was the lower-cost choice.

## Consequences

- Provider swap is genuinely config-only (LLM_PROVIDER=openai|ollama),
  matching the FR-4 architecture acceptance test.
- If a future embedding model doesn't support dimension reduction to
  768, this decision would need revisiting — noted as a known
  constraint, not treated as universally future-proof.
- pgvector's ivfflat index (lists=100) is tuned for low-thousands of
  rows; would need retuning (or a switch to HNSW) if the corpus grows
  by an order of magnitude.