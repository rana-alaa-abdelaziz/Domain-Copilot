"""
SQLAlchemy implementation of the ChunkRepository domain port.
Translates between domain Chunk dataclasses and the ORM Chunk model at
the boundary, same pattern as document_repository.py.
"""
from sqlalchemy.orm import Session

from backend.domain.entities.chunk import Chunk as DomainChunk
from backend.domain.ports.chunk_repository import ChunkRepository
from backend.infrastructure.db.models import Chunk as OrmChunk


class SqlAlchemyChunkRepository(ChunkRepository):
    def __init__(self, session: Session, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    def get_chunks_by_doc(self, doc_id: str) -> list[DomainChunk]:
        orm_chunks = (
            self._session.query(OrmChunk)
            .filter(OrmChunk.doc_id == doc_id)
            .order_by(OrmChunk.chunk_index)
            .all()
        )
        return [self._to_domain(c) for c in orm_chunks]

    def save_chunks(self, chunks: list[DomainChunk]) -> None:
        for chunk in chunks:
            self._session.add(
                OrmChunk(
                    chunk_id=chunk.chunk_id,
                    doc_id=chunk.doc_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    standard_id=chunk.standard_id,
                    hierarchy_path=chunk.hierarchy_path,
                    page=chunk.page,
                    created_at=chunk.created_at,
                )
            )
        if self._auto_commit:
            self._session.commit()

    def delete_chunks_by_doc(self, doc_id: str) -> None:
        self._session.query(OrmChunk).filter(OrmChunk.doc_id == doc_id).delete()
        if self._auto_commit:
            self._session.commit()

    @staticmethod
    def _to_domain(orm_chunk: OrmChunk) -> DomainChunk:
        return DomainChunk(
            chunk_id=orm_chunk.chunk_id,
            doc_id=orm_chunk.doc_id,
            content=orm_chunk.content,
            chunk_index=orm_chunk.chunk_index,
            page=orm_chunk.page,
            created_at=orm_chunk.created_at,
            standard_id=orm_chunk.standard_id,
            hierarchy_path=orm_chunk.hierarchy_path,
        )
