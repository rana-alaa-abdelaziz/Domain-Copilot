"""
Orchestrates FR-2's hybrid retrieval: embed the query, run dense (vector)
and keyword search in parallel result sets, fuse via RRF, return
structured Citations. This is the use case FR-5's "graceful degradation
to plain RAG" falls back TO when the multi-agent path fails — it must
work correctly standalone, with no agent/orchestrator dependency.

over_fetch: dense and keyword search each fetch more than top_k before
fusion, since a chunk might rank low in one list but high in the other —
fusing on a too-small candidate set from either side would silently drop
chunks RRF should have surfaced.
"""

from dataclasses import dataclass

from backend.domain.entities.citation import Citation
from backend.domain.ports import KeywordSearchPort, LlmProvider, VectorStore
from backend.domain.services.retrieval_fusion import reciprocal_rank_fusion

DEFAULT_OVER_FETCH_MULTIPLIER = 4


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    citations: list[Citation]

    @property
    def has_evidence(self) -> bool:
        return len(self.citations) > 0


class HybridRetrieveUseCase:
    def __init__(
        self,
        llm_provider: LlmProvider,
        vector_store: VectorStore,
        keyword_search: KeywordSearchPort,
    ):
        self._llm_provider = llm_provider
        self._vector_store = vector_store
        self._keyword_search = keyword_search

    def execute(
        self, query: str, top_k: int = 5, doc_category: str | None = None
    ) -> RetrievalResult:
        fetch_k = top_k * DEFAULT_OVER_FETCH_MULTIPLIER

        query_vector = self._llm_provider.embed(query)
        dense_results = self._vector_store.query(
            query_vector, top_k=fetch_k, doc_category=doc_category
        )
        keyword_results = self._keyword_search.search(
            query, top_k=fetch_k, doc_category=doc_category
        )

        citations = reciprocal_rank_fusion(dense_results, keyword_results, top_k=top_k)

        return RetrievalResult(query=query, citations=citations)
