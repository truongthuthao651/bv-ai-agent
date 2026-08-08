"""Tests for the document-viewer reconstruction + rendering (app/api/docview.py)."""

from __future__ import annotations

from app.api import docview
from app.auth import is_public_path


def _chunk(
    idx: int, section_path: str, text: str, **extra: object
) -> dict[str, object]:
    return {
        "chunk_index": idx,
        "doc_title": "Quy trình giải quyết quyền lợi",
        "section_path": section_path,
        "display_text": text,
        **extra,
    }


def test_reconstruct_groups_contiguous_sections() -> None:
    chunks = [
        _chunk(0, "Điều 1", "Đoạn A.\n\nĐoạn B."),
        _chunk(1, "Điều 2", "Đoạn C."),
    ]
    title, sections = docview.reconstruct_sections(chunks)
    assert title == "Quy trình giải quyết quyền lợi"
    assert [s["section_path"] for s in sections] == ["Điều 1", "Điều 2"]
    assert sections[0]["text"] == "Đoạn A.\n\nĐoạn B."


def test_reconstruct_removes_block_level_overlap() -> None:
    # chunk 1's trailing block reappears as chunk 2's leading block (overlap).
    chunks = [
        _chunk(0, "Điều 1", "Đoạn A.\n\nĐoạn B."),
        _chunk(1, "Điều 1", "Đoạn B.\n\nĐoạn C."),
    ]
    _, sections = docview.reconstruct_sections(chunks)
    assert len(sections) == 1
    assert sections[0]["text"] == "Đoạn A.\n\nĐoạn B.\n\nĐoạn C."


def test_reconstruct_removes_multi_block_overlap() -> None:
    chunks = [
        _chunk(0, "Điều 1", "A.\n\nB.\n\nC."),
        _chunk(1, "Điều 1", "B.\n\nC.\n\nD."),
    ]
    _, sections = docview.reconstruct_sections(chunks)
    assert sections[0]["text"] == "A.\n\nB.\n\nC.\n\nD."


def test_reconstruct_rebuilds_a_section_from_parent_child_chunks() -> None:
    # The viewer reads stored chunks, which under parent-child chunking are
    # children. They tile their parent on block boundaries and parents overlap
    # by whole blocks, so de-overlapping must still rebuild the exact section.
    from app.ingestion.chunking import chunk_document
    from app.models.schemas import DocType, ParsedDocument, ParsedSection

    text = "\n\n".join(f"Đoạn số {i} về quyền lợi bảo hiểm." for i in range(14))
    doc = ParsedDocument(
        doc_title="Quy trình giải quyết quyền lợi",
        doc_type=DocType.OTHER,
        sections=[ParsedSection(section_path="Điều 1", text=text)],
    )
    chunks = chunk_document(
        doc, "d1", max_tokens=60, overlap_pct=0.12, child_max_tokens=15
    )
    assert len(chunks) > 1
    payloads = [
        {
            "chunk_index": c.chunk_index,
            "doc_title": c.doc_title,
            "section_path": c.section_path,
            "display_text": c.display_text,
        }
        for c in chunks
    ]
    _, sections = docview.reconstruct_sections(payloads)
    assert len(sections) == 1
    assert sections[0]["text"] == text


def test_render_markdown_preserves_math_verbatim() -> None:
    # Underscores inside LaTeX must NOT become Markdown emphasis.
    html_out = docview.render_markdown("Công thức: $_tV_x = A_{x+t} - P_x$ nhé.")
    assert "_tV_x = A_{x+t} - P_x" in html_out or "$_tV_x" in html_out
    assert "<em>" not in html_out


def test_render_markdown_renders_tables() -> None:
    html_out = docview.render_markdown("| Tuổi | Phí |\n|------|-----|\n| 30 | 100 |")
    assert "<table>" in html_out
    assert "<td>30</td>" in html_out


def test_render_page_highlights_requested_section() -> None:
    _, sections = docview.reconstruct_sections(
        [_chunk(0, "Điều 1", "A."), _chunk(1, "Điều 2", "B.")]
    )
    page = docview.render_page("Doc", sections, doc_id="d1", highlight_section="Điều 2")
    # Exactly one section carries the target class, and it's Điều 2's.
    assert page.count('class="doc-section target"') == 1
    idx2 = page.index("Điều 2")
    idx_target = page.index("doc-section target")
    assert idx_target < idx2
    assert "scrollIntoView" in page  # scroll script only emitted when matched


def test_render_page_no_highlight_has_no_scroll_script() -> None:
    _, sections = docview.reconstruct_sections([_chunk(0, "Điều 1", "A.")])
    page = docview.render_page("Doc", sections, doc_id="d1")
    assert "scrollIntoView" not in page
    # No section gets the target class (the string appears only in the CSS rule).
    assert 'class="doc-section target"' not in page


def test_render_page_download_link_only_with_source_file() -> None:
    _, sections = docview.reconstruct_sections([_chunk(0, "Điều 1", "A.")])
    assert "Tải bản gốc" in docview.render_page(
        "Doc", sections, doc_id="d1", has_source_file=True
    )
    assert "Tải bản gốc" not in docview.render_page(
        "Doc", sections, doc_id="d1", has_source_file=False
    )


def test_no_documents_route_is_public() -> None:
    # SEC-A (audit/01-engineering.md §1.4): /view and /file used to be
    # regex-matched into PUBLIC_PREFIXES, meaning no session check at all —
    # anyone who could guess a filename (doc_id is a deterministic uuid5 of
    # it) could read the full document unauthenticated. All /documents routes
    # now require at least a signed-in session; see tests/test_auth.py for
    # the "any account, not just admin" vs. "admin-only" split (list/delete
    # need require_admin on top of this; view/file don't).
    assert not is_public_path("/documents/abc-123/view")
    assert not is_public_path("/documents/abc-123/file")
    assert not is_public_path("/documents")
    assert not is_public_path("/documents/abc-123")
