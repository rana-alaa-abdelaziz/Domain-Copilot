"""
Deterministic PDF text extraction — no AI. Given a file path, returns
cleaned, extracted text plus a SHA256 hash used for idempotency checks
before any chunking or embedding happens.
"""

import hashlib
from collections import Counter
from pathlib import Path

import pymupdf as fitz

# A line repeating on at least this fraction of pages is treated as a
# running header/footer (title, page number, org name, etc.) and stripped
# before chunking — otherwise it gets chunked as if it were real content,
# and its incidental resemblance to a real code can produce false-positive
# standard_id matches on nearly every page.
_HEADER_FOOTER_REPETITION_THRESHOLD = 0.5


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
    raw_pages: list[tuple[int, list[str]]] = []
    for page_number, page in enumerate(doc, start=1):
        raw_text = page.get_text("text")
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        raw_pages.append((page_number, lines))
    doc.close()

    repeated_lines = _find_repeated_lines(raw_pages)

    pages = []
    for page_number, lines in raw_pages:
        content_lines = [line for line in lines if line not in repeated_lines]
        cleaned = "\n".join(content_lines)
        if cleaned:
            pages.append({"page": page_number, "text": cleaned})
    return pages


def _find_repeated_lines(raw_pages: list[tuple[int, list[str]]]) -> set[str]:
    """
    Identifies lines that recur across a large fraction of pages — the
    signature of a running header/footer rather than body content, which
    only very rarely repeats verbatim across many pages.
    """
    if len(raw_pages) < 2:
        return set()
    line_page_counts = Counter()
    for _, lines in raw_pages:
        for line in set(lines):
            line_page_counts[line] += 1
    threshold = max(2, round(len(raw_pages) * _HEADER_FOOTER_REPETITION_THRESHOLD))
    return {line for line, count in line_page_counts.items() if count >= threshold}
