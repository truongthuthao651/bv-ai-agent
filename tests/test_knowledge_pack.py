"""Knowledge-pack tests: source-URL validation and manifest parsing.

The knowledge pack is how public reference material (law, circulars, public
brochures) reaches the assistant WITHOUT putting the app on the network: a
human downloads the files, records their public URLs in a manifest, and the
ingest script indexes them locally. These tests pin the two contracts that
keeps honest — the URL is validated but never fetched, and a manifest entry
whose file is missing is reported rather than downloaded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.ingest import _validate_source_url
from app.models.schemas import Chunk, DocType, ParsedDocument, ParsedSection

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from ingest_knowledge_pack import parse_manifest  # noqa: E402

# --------------------------------------------------------------------------- #
# URL validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "url",
    [
        "https://vanban.chinhphu.vn/luat-08-2022-qh15",
        "http://example.gov.vn/thong-tu",
        "HTTPS://Example.Gov.VN/Van-Ban",
    ],
)
def test_public_http_urls_accepted(url: str) -> None:
    assert _validate_source_url(url) == url.strip()


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_source_url_means_internal_document(blank: str | None) -> None:
    assert _validate_source_url(blank) is None


@pytest.mark.parametrize(
    "url",
    [
        # The value is rendered as a Markdown link target, so anything that
        # isn't http(s) is rejected rather than escaped.
        "javascript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "file:///etc/passwd",
        "ftp://example.com/doc.pdf",
        "vanban.chinhphu.vn/khong-co-scheme",
        "https://example.com/a b",  # would break the Markdown link
        "https://example.com/x)y",  # would close the Markdown link early
    ],
)
def test_non_public_or_unsafe_urls_are_rejected(url: str) -> None:
    with pytest.raises(HTTPException) as exc:
        _validate_source_url(url)
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# source_url flows into the payload
# --------------------------------------------------------------------------- #


def test_source_url_reaches_the_qdrant_payload() -> None:
    url = "https://example.gov.vn/luat"
    chunk = Chunk(
        doc_id="d1",
        doc_title="Luật Kinh doanh bảo hiểm 2022",
        section_path="Điều 12",
        doc_type=DocType.REFERENCE,
        display_text="Nội dung.",
        embed_text="Nội dung.",
        chunk_index=0,
        source_url=url,
    )
    assert chunk.to_payload().source_url == url


def test_chunking_carries_source_url_from_the_parsed_document() -> None:
    from app.ingestion.chunking import chunk_document

    doc = ParsedDocument(
        doc_title="Thông tư",
        doc_type=DocType.REFERENCE,
        sections=[ParsedSection(section_path="Điều 1", text="Nội dung điều 1.")],
        source_url="https://example.gov.vn/tt",
    )
    chunks = chunk_document(doc, "d1")
    assert chunks
    assert all(c.source_url == "https://example.gov.vn/tt" for c in chunks)


# --------------------------------------------------------------------------- #
# Manifest parsing
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_text("# Nội dung công khai\n", encoding="utf-8")
    return path


def test_valid_manifest_entry_defaults_to_reference_type(tmp_path: Path) -> None:
    _write(tmp_path, "luat.md")
    raw = [
        {
            "file": "luat.md",
            "title": "Luật Kinh doanh bảo hiểm 2022",
            "url": "https://example.gov.vn/luat",
        }
    ]
    entries, problems = parse_manifest(raw, tmp_path)
    assert problems == []
    assert len(entries) == 1
    assert entries[0].doc_type is DocType.REFERENCE
    assert entries[0].url == "https://example.gov.vn/luat"
    assert entries[0].department is None


def test_missing_file_is_reported_not_downloaded(tmp_path: Path) -> None:
    raw = [
        {
            "file": "chua_tai_ve.pdf",
            "title": "Thông tư",
            "url": "https://example.gov.vn/tt",
        }
    ]
    entries, problems = parse_manifest(raw, tmp_path)
    assert entries == []
    assert len(problems) == 1
    assert "chua_tai_ve.pdf" in problems[0]
    assert "tải thủ công" in problems[0]


def test_path_traversal_in_manifest_is_rejected(tmp_path: Path) -> None:
    raw = [
        {
            "file": "../../etc/passwd",
            "title": "X",
            "url": "https://example.gov.vn/x",
        }
    ]
    entries, problems = parse_manifest(raw, tmp_path)
    assert entries == []
    assert "nằm ngoài thư mục pack" in problems[0]


def test_unsafe_url_in_manifest_is_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "a.md")
    raw = [{"file": "a.md", "title": "X", "url": "javascript:alert(1)"}]
    entries, problems = parse_manifest(raw, tmp_path)
    assert entries == []
    assert problems


def test_incomplete_entries_are_reported_individually(tmp_path: Path) -> None:
    _write(tmp_path, "ok.md")
    raw = [
        {"file": "ok.md", "title": "Hợp lệ", "url": "https://example.gov.vn/ok"},
        {"file": "ok.md", "title": "Thiếu url"},
        "khong-phai-mapping",
        {
            "file": "ok.md",
            "title": "Sai loại",
            "url": "https://e.gov.vn/x",
            "doc_type": "khong-ton-tai",
        },
    ]
    entries, problems = parse_manifest(raw, tmp_path)
    assert [e.title for e in entries] == ["Hợp lệ"]
    assert len(problems) == 3


def test_manifest_must_be_a_list(tmp_path: Path) -> None:
    entries, problems = parse_manifest({"file": "a.md"}, tmp_path)
    assert entries == []
    assert "danh sách" in problems[0]
