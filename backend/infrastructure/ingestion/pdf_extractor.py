"""
Deterministic PDF text extraction — no AI. Given a file path, returns
cleaned, extracted text plus a SHA256 hash used for idempotency checks
before any chunking or embedding happens.
"""
import hashlib
from pathlib import Path

import pymupdf as fitz


def compute_file_hash(file_path: Path) -> str:
    """SHA256 of the raw file bytes — the idempotency key stored on Document.hash."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_pdf_text(file_path: Path) -> list[dict]:
    """
    Returns one dict per page: {"page": <1-indexed int>, "text": <cleaned str>}.
    Keeping page boundaries here (not flattening to one big string) is what
    lets the chunker later populate Chunk.page accurately.
    """
    doc = fitz.open(file_path)
    pages = []
    for page_number, page in enumerate(doc, start=1):
        raw_text = page.get_text("text")
        cleaned = _clean_text(raw_text)
        if cleaned:
            pages.append({"page": page_number, "text": cleaned})
    doc.close()
    return pages


def _clean_text(raw_text: str) -> str:
    lines = [line.strip() for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)