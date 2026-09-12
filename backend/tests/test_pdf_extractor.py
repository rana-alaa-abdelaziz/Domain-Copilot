import hashlib
from pathlib import Path

import pymupdf as fitz

from backend.infrastructure.ingestion.pdf_extractor import (
    _find_repeated_lines,
    compute_file_hash,
    extract_pdf_text,
)


def test_compute_file_hash(tmp_path: Path):
    test_file = tmp_path / "sample.txt"
    content = b"Deterministic PDF text extraction test payload"
    test_file.write_bytes(content)

    expected_hash = hashlib.sha256(content).hexdigest()
    assert compute_file_hash(test_file) == expected_hash


def test_find_repeated_lines_single_or_empty_page():
    assert _find_repeated_lines([]) == set()
    assert _find_repeated_lines([(1, ["Header", "Content", "Footer"])]) == set()


def test_find_repeated_lines_identifies_frequent_lines():
    raw_pages = [
        (1, ["Standard Document Header", "Page 1 Content", "Footer line"]),
        (2, ["Standard Document Header", "Page 2 Content", "Footer line"]),
        (3, ["Standard Document Header", "Page 3 Content", "Different footer"]),
        (4, ["Standard Document Header", "Page 4 Content", "Another footer"]),
    ]
    # Header repeats on 4/4 pages (1.0 >= 0.5) -> identified
    # "Footer line" repeats on 2/4 pages (0.5 >= 0.5) -> identified
    # Page contents repeat on 1/4 pages -> not identified
    repeated = _find_repeated_lines(raw_pages)
    assert "Standard Document Header" in repeated
    assert "Footer line" in repeated
    assert "Page 1 Content" not in repeated
    assert "Page 2 Content" not in repeated


def test_extract_pdf_text_strips_running_header_and_footer(tmp_path: Path):
    pdf_path = tmp_path / "test_doc.pdf"
    doc = fitz.open()

    for i in range(1, 5):
        page = doc.new_page()
        text = (
            f"Acme Corp Confidential Report\n\n"
            f"Section {i}: Content for page {i}\n"
            f"Details regarding standard implementation {i}.\n\n"
            f"Page Footer - Confidential"
        )
        page.insert_text((50, 50), text)

    doc.save(str(pdf_path))
    doc.close()

    extracted = extract_pdf_text(pdf_path)
    assert len(extracted) == 4

    for page_dict in extracted:
        text = page_dict["text"]
        # Running header and footer should be stripped
        assert "Acme Corp Confidential Report" not in text
        assert "Page Footer - Confidential" not in text
        # Unique page content should be preserved
        assert f"Content for page {page_dict['page']}" in text
