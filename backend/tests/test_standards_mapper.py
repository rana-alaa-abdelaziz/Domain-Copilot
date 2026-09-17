from unittest.mock import MagicMock

from backend.application.agents.standards_mapper import StandardsMapper
from backend.application.use_cases.hybrid_retrieve import (
    HybridRetrieveUseCase,
    RetrievalResult,
)
from backend.domain.entities.citation import Citation
from backend.domain.ports import LlmProvider


def _make_citation(chunk_id: str, content: str) -> Citation:
    return Citation(
        chunk_id=chunk_id,
        doc_id="doc-1",
        page=1,
        standard_id="std-1",
        content=content,
        fused_score=0.9,
        dense_rank=1,
        keyword_rank=1,
        source="test",
    )


def test_standards_mapper_deterministic_matching():
    # 1. Mock retrieval use case
    mock_retrieval = MagicMock(spec=HybridRetrieveUseCase)

    # Side 1 Requirement chunks
    side1_citations = [
        _make_citation("chunk-req-1", "Required: RESTful APIs and Git."),
        _make_citation(
            "chunk-req-2", "Must have Relational Database Design SQL and Unit Testing."
        ),
    ]

    # Side 2 Reference Curriculum chunks
    side2_api_citations = [
        _make_citation(
            "chunk-curr-api", "Syllabus covers REST API endpoints and HTTP methods."
        )
    ]
    side2_git_citations = [
        _make_citation("chunk-curr-git", "Syllabus covers Git branching and commits.")
    ]

    def mock_retrieve_execute(query, top_k, doc_category):
        if doc_category == "requirement":
            return RetrievalResult(query=query, citations=side1_citations)
        if "API" in query:
            return RetrievalResult(query=query, citations=side2_api_citations)
        if "Git" in query:
            return RetrievalResult(query=query, citations=side2_git_citations)
        return RetrievalResult(query=query, citations=[])

    mock_retrieval.execute.side_effect = mock_retrieve_execute

    # 2. Mock LLM provider completing with clean JSON array of competencies
    mock_llm = MagicMock(spec=LlmProvider)
    mock_llm.complete.return_value = '["RESTful API Design", "Git Version Control", "Relational Database SQL", "Unit Testing"]'

    agent = StandardsMapper(retrieve_use_case=mock_retrieval, llm_provider=mock_llm)

    report = agent.run(
        target_role="Junior Backend Developer",
        user_reported_subjects=["REST API Design", "Git Version Control"],
    )

    assert report.target_role == "Junior Backend Developer"
    assert len(report.gaps) == 4

    covered = report.covered_competencies
    unverified = report.unverified_competencies

    assert len(covered) == 2
    assert len(unverified) == 2

    # Verify citation grounding and domain invariants
    for gap in report.gaps:
        assert len(gap.required_by_chunk_ids) > 0
        assert gap.severity in {"critical", "moderate", "minor"}
        assert gap.coverage_source in {
            "corpus_citation",
            "model_inference",
            "unverified",
        }

    api_gap = next(g for g in report.gaps if "API" in g.competency)
    assert api_gap.coverage_source == "corpus_citation"
    assert "chunk-curr-api" in api_gap.coverage_chunk_ids

    sql_gap = next(g for g in report.gaps if "SQL" in g.competency)
    assert sql_gap.coverage_source == "unverified"
    assert sql_gap.severity == "critical"

def test_hybrid_matching_deterministic_primary():
    mock_retrieval = MagicMock(spec=HybridRetrieveUseCase)
    mock_llm = MagicMock(spec=LlmProvider)
    mock_llm.embed.return_value = [1.0, 0.0, 0.0]
    
    agent = StandardsMapper(retrieve_use_case=mock_retrieval, llm_provider=mock_llm)
    
    # Reset mock after init computes canonical embeddings
    mock_llm.embed.reset_mock()
    
    # "React Component Design" and "Frontend Developer" both match the "frontend" domain deterministically
    match = agent._find_matching_subject("React Component Design", ["Frontend Developer"])
    
    assert match == "Frontend Developer"
    mock_llm.embed.assert_not_called()

def test_hybrid_matching_fallback_success():
    mock_retrieval = MagicMock(spec=HybridRetrieveUseCase)
    mock_llm = MagicMock(spec=LlmProvider)
    
    def mock_embed(text):
        if text == "frontend":
            return [1.0, 0.0, 0.0]
        if text == "Browser Client Development":
            # Similarity with [1.0, 0.0, 0.0] is 0.8 (> 0.65)
            return [0.8, 0.6, 0.0]
        return [0.0, 1.0, 0.0]
        
    mock_llm.embed.side_effect = mock_embed
    
    agent = StandardsMapper(retrieve_use_case=mock_retrieval, llm_provider=mock_llm)
    mock_llm.embed.reset_mock()
    mock_llm.embed.side_effect = mock_embed
    
    # "Browser Client Development" doesn't hit deterministic keywords, triggering fallback
    match = agent._find_matching_subject("React Component Design", ["Browser Client Development"])
    
    assert match == "Browser Client Development"
    mock_llm.embed.assert_called_with("Browser Client Development")

def test_hybrid_matching_fallback_failure():
    mock_retrieval = MagicMock(spec=HybridRetrieveUseCase)
    mock_llm = MagicMock(spec=LlmProvider)
    
    def mock_embed(text):
        if text == "frontend":
            return [1.0, 0.0, 0.0]
        if text == "Baking a cake":
            # Similarity with [1.0, 0.0, 0.0] is 0.0 (< 0.65)
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]
        
    mock_llm.embed.side_effect = mock_embed
    
    agent = StandardsMapper(retrieve_use_case=mock_retrieval, llm_provider=mock_llm)
    mock_llm.embed.reset_mock()
    mock_llm.embed.side_effect = mock_embed
    
    match = agent._find_matching_subject("React Component Design", ["Baking a cake"])
    
    assert match is None
    mock_llm.embed.assert_called_with("Baking a cake")
