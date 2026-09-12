# backend/infrastructure/db/models.py
"""
SQLAlchemy ORM models. Lives entirely in infrastructure/ — domain/entities
stays plain Pydantic and must never import from this file.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    DDL,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

# Must match backend/infrastructure/db/migrations/versions/0002_add_chunk_embedding.py
EMBEDDING_DIM = 768

Base = declarative_base()
event.listen(
    Base.metadata,
    "before_create",
    DDL("CREATE EXTENSION IF NOT EXISTS vector;").execute_if(dialect="postgresql"),
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IngestionStatusEnum(str, PyEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "document"

    doc_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source = Column(String, nullable=False)            # filename or origin reference
    version = Column(String, nullable=False)
    hash = Column(String, nullable=False, unique=True)  # SHA256 — idempotency key
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    ingestion_status = relationship(
        "IngestionStatus", back_populates="document", uselist=False, cascade="all, delete-orphan"
    )
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class IngestionStatus(Base):
    __tablename__ = "ingestion_status"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    doc_id = Column(UUID(as_uuid=False), ForeignKey("document.doc_id"), nullable=False, unique=True)
    status = Column(
        Enum(
            IngestionStatusEnum,
            name="ingestion_status_enum",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=IngestionStatusEnum.PENDING,
    )
    error_message = Column(Text, nullable=True)         # populated only when status == FAILED
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    document = relationship("Document", back_populates="ingestion_status")


class Chunk(Base):
    __tablename__ = "chunk"

    chunk_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    doc_id = Column(UUID(as_uuid=False), ForeignKey("document.doc_id"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)       # order within the document
    standard_id = Column(String, nullable=True)         # nullable: not every chunk maps to a standard
    hierarchy_path = Column(String, nullable=True)      # e.g. "framework > competency > indicator"
    page = Column(String, nullable=True)                # page number or clause/section reference
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True)  # null until EmbedChunksUseCase runs

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("doc_id", "chunk_index", name="uq_chunk_doc_order"),
    )