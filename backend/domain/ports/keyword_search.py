"""
Port for keyword/full-text search — the second half of hybrid retrieval
alongside VectorStore's dense search. Kept as a separate port (not folded
into VectorStore) because it's a genuinely different retrieval mechanism
with its own backing index; a future swap to a dedicated search engine
would replace only the infrastructure adapter, same boundary VectorStore
already establishes.
"""

from abc import ABC, abstractmethod


class KeywordSearchPort(ABC):
    @abstractmethod
    def search(
        self, query_text: str, top_k: int = 5, doc_category: str | None = None
    ) -> list[dict]:
        """Returns rows shaped like VectorStore.query()'s output —
        chunk_id, doc_id, content, page, standard_id, score — so the
        fusion step can treat both result sets uniformly.

        doc_category: when provided, restricts results to chunks whose
        parent document has this category (e.g. "requirement") — the
        metadata-filtering enhancement backing the Standards Mapper's
        dual-sided grounding (role requirements vs. reference material).
        None means unfiltered, the existing default behavior."""
