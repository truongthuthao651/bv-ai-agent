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


def test_viewer_routes_are_public_but_list_and_delete_are_not() -> None:
    assert is_public_path("/documents/abc-123/view")
    assert is_public_path("/documents/abc-123/file")
    # The admin list + per-doc DELETE target must stay gated.
    assert not is_public_path("/documents")
    assert not is_public_path("/documents/abc-123")
