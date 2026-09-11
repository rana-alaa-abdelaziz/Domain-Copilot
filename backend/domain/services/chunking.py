"""
Chunking strategy per ADR-001: chunk along the extractor's natural
boundaries first (one chunk per page/section), splitting further on
paragraph breaks only when a section exceeds MAX_CHUNK_CHARS.
"""
import re
import uuid
from datetime import datetime, timezone

from backend.domain.entities.chunk import Chunk

MAX_CHUNK_CHARS = 1500
_STANDARD_ID_PATTERN = re.compile(r"\b[A-Z]{2,5}[-.][0-9]+(?:\.[0-9]+)*\b")


def chunk_sections(doc_id: str, sections: list[dict]) -> list[Chunk]:
    chunks: list[Chunk] = []
    index = 0
    for section in sections:
        page_label = section["page"]
        text = section["text"]
        for piece in _split_if_oversized(text):
            chunks.append(
                Chunk(
                    chunk_id=str(uuid.uuid4()),
                    doc_id=doc_id,
                    content=piece,
                    chunk_index=index,
                    page=page_label,
                    created_at=datetime.now(timezone.utc),
                    standard_id=_extract_standard_id(piece),
                    hierarchy_path=page_label,
                )
            )
            index += 1
    return chunks


def _split_if_oversized(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    pieces: list[str] = []
    current = ""
    for para in paragraphs:
        candidate = f"{current}\n{para}".strip() if current else para
        if len(candidate) > MAX_CHUNK_CHARS and current:
            pieces.append(current)
            current = para
        else:
            current = candidate
    if current:
        pieces.append(current)
    final_pieces: list[str] = []
    for piece in pieces:
        if len(piece) <= MAX_CHUNK_CHARS:
            final_pieces.append(piece)
        else:
            for i in range(0, len(piece), MAX_CHUNK_CHARS):
                final_pieces.append(piece[i:i + MAX_CHUNK_CHARS])
    return final_pieces


def _extract_standard_id(text: str) -> str | None:
    match = _STANDARD_ID_PATTERN.search(text)
    return match.group(0) if match else None
