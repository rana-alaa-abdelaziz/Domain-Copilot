import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.application.agents.assessment_generator import AssessmentGenerator
from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.entities.assessment_item import validate_item_semantics
from backend.domain.entities.competency_gap_report import (
    CompetencyGap,
    CompetencyGapReport,
)
from backend.infrastructure.config import get_instrumented_llm_provider
from backend.infrastructure.db.repositories.document_repository import (
    SqlAlchemyDocumentRepository,
)
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore


async def main():
    engine = create_engine("postgresql://postgres:postgres@localhost:5432/domain_copilot")
    with Session(engine) as session:
        doc_repo = SqlAlchemyDocumentRepository(session)
        vec_store = PgVectorStore(session)
        kw_search = PgKeywordSearch(session)
        
        retrieve_uc = HybridRetrieveUseCase(
            llm_provider=get_instrumented_llm_provider(session),
            vector_store=vec_store,
            keyword_search=kw_search
        )
        llm = get_instrumented_llm_provider(session)
        
        generator = AssessmentGenerator(retrieve_uc, llm)
        
        # Simulating the UI gap report
        gap_report = CompetencyGapReport(
            target_role="FrontEnd developer",
            gaps=[
                CompetencyGap(competency="CSS", severity="critical", coverage_source="unverified", matched_user_subject="react"),
                CompetencyGap(competency="JavaScript", severity="critical", coverage_source="unverified", matched_user_subject="react"),
                CompetencyGap(competency="API Design", severity="critical", coverage_source="unverified", matched_user_subject=None),
                CompetencyGap(competency="RESTful APIs", severity="critical", coverage_source="unverified", matched_user_subject=None),
            ]
        )
        
        # Monkey patch _build_item to test validate_item_semantics manually
        original_build = generator._build_item
        def mock_build_item(data, subject, role, chunks):
            item = original_build(data, subject, role, chunks)
            probs = validate_item_semantics(item)
            if probs:
                print(f"FAILED VALIDATION for question: {item.question_text}\nProblems: {probs}")
            return item
        generator._build_item = mock_build_item
        
        report = generator.generate_items(gap_report)
        print("Final items length:", len(report.items))

if __name__ == "__main__":
    asyncio.run(main())
