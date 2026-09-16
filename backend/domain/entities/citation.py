"""
Structured citation returned by retrieval — FR-2 requires citations be
traceable to the exact chunk, not just a document name. Carries enough
for a reviewer or the API response to show provenance without a second
lookup: chunk_id (the traceable key), doc_id, page/section, standard_id,
and the two component scores plus the fused rank so retrieval quality is
inspectable, not just a black-box ordering.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Citation:
    chunk_id: str
    doc_id: str
    source: str
    content: str
    page: str | None
    standard_id: str | None
    fused_score: float
    dense_rank: int | None
    keyword_rank: int | None
