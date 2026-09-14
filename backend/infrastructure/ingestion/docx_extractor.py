"""
Deterministic DOCX text extraction — no AI. Mirrors pdf_extractor.py's
output shape so the chunker downstream can treat both formats uniformly.

DOCX has no native "page" concept (pagination is a rendering-time thing,
not stored in the file), so this uses heading-based sections instead of
page numbers — Chunk.page will store a section label for DOCX-sourced
chunks rather than a page number.
"""

from pathlib import Path

from docx import Document as DocxDocument


def extract_docx_text(file_path: Path) -> list[dict]:
    """
    Returns one dict per section: {"page": <section label str>, "text": <cleaned str>}.
    A new section starts at each Heading-style paragraph; body text
    accumulates under the most recent heading seen so far.
    """
    doc = DocxDocument(file_path)
    sections: list[dict] = []
    current_label = "Document Start"
    current_lines: list[str] = []

    def _flush():
        text = _clean_text("\n".join(current_lines))
        if text:
            sections.append({"page": current_label, "text": text})

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style is not None and para.style.name.startswith("Heading"):
            _flush()
            current_label = text
            current_lines = []
        else:
            current_lines.append(text)

    _flush()
    return sections


def _clean_text(raw_text: str) -> str:
    lines = [line.strip() for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)
