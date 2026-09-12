"""Unit tests for reciprocal_rank_fusion — pure function, no DB needed."""
from backend.domain.services.retrieval_fusion import RRF_K, reciprocal_rank_fusion


def _row(chunk_id: str, doc_id: str = "doc-1", content: str = "content") -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "content": content,
        "page": "1",
        "standard_id": None,
    }


def test_chunk_in_both_lists_outranks_chunk_in_one_list():
    # "a" appears at rank 1 in both lists; "b" only in dense at rank 2.
    dense = [_row("a"), _row("b")]
    keyword = [_row("a")]

    results = reciprocal_rank_fusion(dense, keyword, top_k=5)

    assert [c.chunk_id for c in results] == ["a", "b"]
    assert results[0].dense_rank == 1
    assert results[0].keyword_rank == 1
    assert results[1].dense_rank == 2
    assert results[1].keyword_rank is None


def test_fused_score_matches_rrf_formula_exactly():
    dense = [_row("a"), _row("b")]
    keyword = [_row("b"), _row("a")]

    results = reciprocal_rank_fusion(dense, keyword, top_k=5)
    scores = {c.chunk_id: c.fused_score for c in results}

    # a: dense rank 1, keyword rank 2 -> 1/(60+1) + 1/(60+2)
    # b: dense rank 2, keyword rank 1 -> 1/(60+2) + 1/(60+1)
    # Symmetric inputs -> identical scores for both.
    expected = 1.0 / (RRF_K + 1) + 1.0 / (RRF_K + 2)
    assert abs(scores["a"] - expected) < 1e-12
    assert abs(scores["b"] - expected) < 1e-12


def test_chunk_only_in_keyword_results_still_appears():
    dense = [_row("a")]
    keyword = [_row("z")]

    results = reciprocal_rank_fusion(dense, keyword, top_k=5)
    ids = {c.chunk_id for c in results}

    assert "z" in ids
    z = next(c for c in results if c.chunk_id == "z")
    assert z.dense_rank is None
    assert z.keyword_rank == 1


def test_top_k_limits_result_count():
    dense = [_row(f"chunk-{i}") for i in range(10)]
    keyword: list[dict] = []

    results = reciprocal_rank_fusion(dense, keyword, top_k=3)

    assert len(results) == 3
    # Highest dense rank (rank 1) must come first.
    assert results[0].chunk_id == "chunk-0"


def test_empty_inputs_return_empty_list():
    assert reciprocal_rank_fusion([], [], top_k=5) == []
