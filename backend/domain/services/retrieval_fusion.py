"""
Reciprocal Rank Fusion (RRF) — combines dense and keyword result lists
into a single ranked list, per FR-2's "documented fusion method"
requirement.

Formula (Cormack, Clarke & Buettcher, 2009 — the standard RRF used in
hybrid search): for each result, score = 1 / (k + rank), summed across
whichever result lists it appears in (rank is 1-indexed position within
that list). k=60 is the constant from the original paper and is what
most hybrid-search implementations use unchanged — it dampens the effect
of small rank differences at the top of either list.

Pure domain logic — no SQLAlchemy, no I/O. Takes two already-fetched
result lists (dicts shaped like PgVectorStore.query() / PgKeywordSearch's
output) and returns Citation entities ranked by fused score.
"""

from backend.domain.entities.citation import Citation

RRF_K = 60


def reciprocal_rank_fusion(
    dense_results: list[dict],
    keyword_results: list[dict],
    top_k: int = 5,
) -> list[Citation]:
    dense_ranks: dict[str, int] = {
        row["chunk_id"]: rank for rank, row in enumerate(dense_results, start=1)
    }
    keyword_ranks: dict[str, int] = {
        row["chunk_id"]: rank for rank, row in enumerate(keyword_results, start=1)
    }

    # Union of chunk_ids across both lists, keeping one representative row
    # per chunk_id for the metadata fields (content, page, standard_id) —
    # dense and keyword results describe the same chunk identically since
    # both read from the same chunk table, so either copy is authoritative.
    rows_by_id: dict[str, dict] = {}
    for row in dense_results:
        rows_by_id[row["chunk_id"]] = row
    for row in keyword_results:
        rows_by_id.setdefault(row["chunk_id"], row)

    fused_scores: dict[str, float] = {}
    for chunk_id in rows_by_id:
        score = 0.0
        if chunk_id in dense_ranks:
            score += 1.0 / (RRF_K + dense_ranks[chunk_id])
        if chunk_id in keyword_ranks:
            score += 1.0 / (RRF_K + keyword_ranks[chunk_id])
        fused_scores[chunk_id] = score

    ranked_ids = sorted(
        rows_by_id.keys(), key=lambda cid: fused_scores[cid], reverse=True
    )

    citations = []
    for chunk_id in ranked_ids[:top_k]:
        row = rows_by_id[chunk_id]
        citations.append(
            Citation(
                chunk_id=chunk_id,
                doc_id=row["doc_id"],
                source=row.get("source", "Unknown"),
                content=row["content"],
                page=row.get("page"),
                standard_id=row.get("standard_id"),
                fused_score=fused_scores[chunk_id],
                dense_rank=dense_ranks.get(chunk_id),
                keyword_rank=keyword_ranks.get(chunk_id),
            )
        )
    return citations
