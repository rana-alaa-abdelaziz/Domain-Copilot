import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.application.use_cases.hybrid_retrieve import HybridRetrieveUseCase
from backend.domain.ports import LlmProvider
from backend.infrastructure.db.models import (
    Base,
)
from backend.infrastructure.db.models import (
    Chunk as OrmChunk,
)
from backend.infrastructure.db.models import (
    Document as OrmDocument,
)
from backend.infrastructure.db.models import (
    IngestionStatus as OrmIngestionStatus,
)
from backend.infrastructure.vectorstore.pg_keyword_search import PgKeywordSearch
from backend.infrastructure.vectorstore.pgvector_store import PgVectorStore

load_dotenv()
RAW_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/domain_copilot_test"
)
DB_URL = (
    RAW_DB_URL.replace("postgresql://", "postgresql+psycopg2://", 1)
    if RAW_DB_URL.startswith("postgresql://")
    else RAW_DB_URL
)


@pytest.fixture
def db_session():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.query(OrmChunk).delete()
    session.query(OrmIngestionStatus).delete()
    session.query(OrmDocument).delete()
    session.commit()
    yield session
    session.query(OrmChunk).delete()
    session.query(OrmIngestionStatus).delete()
    session.query(OrmDocument).delete()
    session.commit()
    session.close()


class StubQueryLlmProvider(LlmProvider):
    def __init__(self, query_mapping: dict[str, list[float]] | None = None):
        self._mapping = query_mapping or {}
        self._default = [0.0] * 768

    def complete(self, prompt: str, **kwargs) -> str:
        return "stub"

    def stream(self, prompt: str, **kwargs):
        yield "stub"

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        return {"tool": None, "arguments": {}}

    def embed(self, text: str) -> list[float]:
        return self._mapping.get(text, self._default)


def _seed_document_and_chunks(session):
    doc_id = str(uuid.uuid4())
    doc = OrmDocument(
        doc_id=doc_id,
        source="standards_test.pdf",
        version="1.0",
        hash="test_hash_123",
        created_at=datetime.now(timezone.utc),
    )
    session.add(doc)

    # Vector 1: first component 1.0, rest 0.0
    vec1 = [1.0] + [0.0] * 767
    # Vector 2: second component 1.0, rest 0.0 (orthogonal to vec1)
    vec2 = [0.0, 1.0] + [0.0] * 766

    chunk_a = OrmChunk(
        chunk_id=str(uuid.uuid4()),
        doc_id=doc_id,
        content="PostgreSQL full-text search with tsvector indexing for high performance retrieval",
        chunk_index=0,
        page=1,
        standard_id="STD-POSTGRES-1",
        embedding=vec1,
        created_at=datetime.now(timezone.utc),
    )
    chunk_b = OrmChunk(
        chunk_id=str(uuid.uuid4()),
        doc_id=doc_id,
        content="PostgreSQL relational database administration and tuning guidelines",
        chunk_index=1,
        page=2,
        standard_id="STD-POSTGRES-2",
        embedding=vec2,
        created_at=datetime.now(timezone.utc),
    )
    chunk_c = OrmChunk(
        chunk_id=str(uuid.uuid4()),
        doc_id=doc_id,
        content="Unrelated culinary arts guide for preparing artisan Italian pasta",
        chunk_index=2,
        page=3,
        standard_id=None,
        embedding=vec1,
        created_at=datetime.now(timezone.utc),
    )

    session.add_all([chunk_a, chunk_b, chunk_c])
    session.commit()
    return doc_id, chunk_a, chunk_b, chunk_c


def test_hybrid_retrieve_returns_fused_results_ranked_by_rrf(db_session):
    _, chunk_a, _chunk_b, _chunk_c = _seed_document_and_chunks(db_session)

    vec1 = [1.0] + [0.0] * 767
    llm = StubQueryLlmProvider(query_mapping={"PostgreSQL search": vec1})
    vector_store = PgVectorStore(db_session)
    keyword_search = PgKeywordSearch(db_session)

    use_case = HybridRetrieveUseCase(
        llm_provider=llm,
        vector_store=vector_store,
        keyword_search=keyword_search,
    )

    result = use_case.execute(query="PostgreSQL search", top_k=3)

    assert result.has_evidence is True
    assert len(result.citations) > 0

    # chunk_a matches BOTH dense (vec1 match) and keyword ("PostgreSQL search")
    # therefore chunk_a should be top-ranked by RRF
    top = result.citations[0]
    assert top.chunk_id == chunk_a.chunk_id
    assert top.dense_rank is not None
    assert top.keyword_rank is not None
    assert top.standard_id == "STD-POSTGRES-1"
    assert top.fused_score > 0.0

    # Fused scores should be strictly descending
    scores = [c.fused_score for c in result.citations]
    assert scores == sorted(scores, reverse=True)


def test_hybrid_retrieve_degrades_gracefully_on_empty_dense_results(db_session):
    _, _chunk_a, chunk_b, _ = _seed_document_and_chunks(db_session)

    # Use an orthogonal vector that does not match any stored vectors (distance >= 1.0)
    vec_orthogonal = [0.0, 0.0, 1.0] + [0.0] * 765
    llm = StubQueryLlmProvider(query_mapping={"relational database": vec_orthogonal})
    vector_store = PgVectorStore(db_session)
    keyword_search = PgKeywordSearch(db_session)

    use_case = HybridRetrieveUseCase(
        llm_provider=llm,
        vector_store=vector_store,
        keyword_search=keyword_search,
    )

    result = use_case.execute(query="relational database", top_k=3)

    # Keyword search should still find chunk_b
    assert result.has_evidence is True
    found_ids = [c.chunk_id for c in result.citations]
    assert chunk_b.chunk_id in found_ids

    # For pure keyword matches where dense search returned empty, dense_rank must be None
    for cit in result.citations:
        assert cit.dense_rank is None
        assert cit.keyword_rank is not None
        assert cit.fused_score > 0.0


def test_hybrid_retrieve_returns_no_evidence_for_nonsense_query(db_session):
    _seed_document_and_chunks(db_session)

    # Orthogonal / non-matching vector and nonsense keyword text
    vec_orthogonal = [0.0, 0.0, 1.0] + [0.0] * 765
    nonsense_query = "xyzzy999randomgibberish12345"
    llm = StubQueryLlmProvider(query_mapping={nonsense_query: vec_orthogonal})
    vector_store = PgVectorStore(db_session)
    keyword_search = PgKeywordSearch(db_session)

    use_case = HybridRetrieveUseCase(
        llm_provider=llm,
        vector_store=vector_store,
        keyword_search=keyword_search,
    )

    result = use_case.execute(query=nonsense_query, top_k=3)

    assert result.has_evidence is False
    assert len(result.citations) == 0