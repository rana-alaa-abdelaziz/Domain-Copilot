import pytest

from backend.domain.services.chunking import (
    MAX_CHUNK_CHARS,
    _extract_standard_id,
    chunk_sections,
)


@pytest.mark.parametrize(
    ("text", "expected_id"),
    [
        ("According to ISO-9001 quality management guidelines.", "ISO-9001"),
        ("Refer to IEEE-802.11 wireless standard.", "IEEE-802.11"),
        ("As defined in NIST.800.53 security controls.", "NIST.800.53"),
        ("Aligned with SSC/Q0508 qualification file.", "SSC/Q0508"),
        ("Under ISO/IEC27001 compliance standards.", "ISO/IEC27001"),
        ("Following BS/7799 best practices.", "BS/7799"),
        ("Standard EN/12345 specifies requirements.", "EN/12345"),
        ("Plain content with no standard identifiers.", None),
        ("Invalid small prefix A/123 is ignored.", None),
        ("Invalid long prefix TOOLONG/123 is ignored.", None),
    ],
)
def test_extract_standard_id(text: str, expected_id: str | None):
    assert _extract_standard_id(text) == expected_id


def test_chunk_sections_extracts_slash_standard_ids():
    sections = [
        {
            "page": 1,
            "text": "Header info.\nQualification Code: SSC/Q0508 for Junior Developer.",
        },
        {
            "page": 2,
            "text": "General curriculum module details without any standard code.",
        },
    ]

    chunks = chunk_sections(doc_id="doc-42", sections=sections)
    assert len(chunks) == 2

    assert chunks[0].doc_id == "doc-42"
    assert chunks[0].page == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].standard_id == "SSC/Q0508"

    assert chunks[1].doc_id == "doc-42"
    assert chunks[1].page == 2
    assert chunks[1].chunk_index == 1
    assert chunks[1].standard_id is None


def test_chunk_sections_splits_oversized():
    long_para = "Word " * (MAX_CHUNK_CHARS // 3)
    text = f"{long_para}\n\n{long_para}\n\n{long_para}\n\n{long_para}"
    sections = [{"page": 1, "text": text}]

    chunks = chunk_sections(doc_id="doc-oversized", sections=sections)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= MAX_CHUNK_CHARS
        assert chunk.doc_id == "doc-oversized"
        assert chunk.page == 1
