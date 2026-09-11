"""
SQLAlchemy implementation of the DocumentRepository domain port.
Translates between domain dataclasses and SQLAlchemy ORM models at the boundary.
"""

from sqlalchemy.orm import Session

from backend.domain.entities.document import (
    Document as DomainDocument,
)
from backend.domain.entities.document import (
    IngestionStatus as DomainIngestionStatus,
)
from backend.domain.entities.document import (
    IngestionStatusEnum as DomainIngestionStatusEnum,
)
from backend.domain.ports.document_repository import DocumentRepository
from backend.infrastructure.db.models import (
    Document as OrmDocument,
)
from backend.infrastructure.db.models import (
    IngestionStatus as OrmIngestionStatus,
)
from backend.infrastructure.db.models import (
    IngestionStatusEnum as OrmIngestionStatusEnum,
)


class SqlAlchemyDocumentRepository(DocumentRepository):
    def __init__(self, session: Session, auto_commit: bool = True):
        self._session = session
        self._auto_commit = auto_commit

    def get_by_hash(self, file_hash: str) -> DomainDocument | None:
        orm_doc = (
            self._session.query(OrmDocument)
            .filter(OrmDocument.hash == file_hash)
            .first()
        )
        if orm_doc is None:
            return None
        return self._to_domain_document(orm_doc)

    def get_by_id(self, doc_id: str) -> DomainDocument | None:
        orm_doc = (
            self._session.query(OrmDocument)
            .filter(OrmDocument.doc_id == doc_id)
            .first()
        )
        if orm_doc is None:
            return None
        return self._to_domain_document(orm_doc)

    def save_document(self, document: DomainDocument) -> None:
        orm_doc = (
            self._session.query(OrmDocument)
            .filter(OrmDocument.doc_id == document.doc_id)
            .first()
        )
        if orm_doc is not None:
            orm_doc.source = document.source
            orm_doc.version = document.version
            orm_doc.hash = document.hash
            orm_doc.updated_at = document.updated_at
        else:
            orm_doc = OrmDocument(
                doc_id=document.doc_id,
                source=document.source,
                version=document.version,
                hash=document.hash,
                created_at=document.created_at,
                updated_at=document.updated_at,
            )
            self._session.add(orm_doc)

        if self._auto_commit:
            self._session.commit()

    def save_ingestion_status(self, status: DomainIngestionStatus) -> None:
        orm_status = (
            self._session.query(OrmIngestionStatus)
            .filter(OrmIngestionStatus.doc_id == status.doc_id)
            .first()
        )
        enum_val = OrmIngestionStatusEnum(status.status.value.lower())
        if orm_status is not None:
            orm_status.status = enum_val
            orm_status.error_message = status.error_message
            orm_status.updated_at = status.updated_at
        else:
            orm_status = OrmIngestionStatus(
                id=status.id,
                doc_id=status.doc_id,
                status=enum_val,
                error_message=status.error_message,
                updated_at=status.updated_at,
            )
            self._session.add(orm_status)

        if self._auto_commit:
            self._session.commit()

    def get_ingestion_status(self, doc_id: str) -> DomainIngestionStatus | None:
        orm_status = (
            self._session.query(OrmIngestionStatus)
            .filter(OrmIngestionStatus.doc_id == doc_id)
            .first()
        )
        if orm_status is None:
            return None
        return self._to_domain_ingestion_status(orm_status)

    @staticmethod
    def _to_domain_document(orm_doc: OrmDocument) -> DomainDocument:
        return DomainDocument(
            doc_id=orm_doc.doc_id,
            source=orm_doc.source,
            version=orm_doc.version,
            hash=orm_doc.hash,
            created_at=orm_doc.created_at,
            updated_at=orm_doc.updated_at,
        )

    @staticmethod
    def _to_domain_ingestion_status(orm_status: OrmIngestionStatus) -> DomainIngestionStatus:
        return DomainIngestionStatus(
            id=orm_status.id,
            doc_id=orm_status.doc_id,
            status=DomainIngestionStatusEnum(orm_status.status.value.lower()),
            updated_at=orm_status.updated_at,
            error_message=orm_status.error_message,
        )
