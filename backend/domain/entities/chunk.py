"""
Plain domain entity for a chunk — no SQLAlchemy, no framework imports.
Mirrors infrastructure/db/models.py's Chunk table; infrastructure maps
between the two at the repository boundary, same pattern as document.py.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    content: str
    chunk_index: int
    page: str | None
    created_at: datetime
    standard_id: str | None = None
    hierarchy_path: str | None = None
    embedding: list[float] | None = None
