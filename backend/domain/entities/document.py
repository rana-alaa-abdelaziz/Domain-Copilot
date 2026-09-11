"""
Plain domain entities — no SQLAlchemy, no framework imports. These are
what the application layer works with; infrastructure maps them to/from
ORM models at the boundary.
"""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class IngestionStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

    @classmethod
    def _missing_(cls, value):
        if isinstance(value, str):
            for member in cls:
                if member.value == value.lower() or member.name == value.upper():
                    return member
        return None


@dataclass
class Document:
    doc_id: str
    source: str
    version: str
    hash: str
    created_at: datetime
    updated_at: datetime


@dataclass
class IngestionStatus:
    id: str
    doc_id: str
    status: IngestionStatusEnum
    updated_at: datetime
    error_message: str | None = None