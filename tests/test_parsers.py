"""Parser tests — Markdown sectionizer + Vietnamese hierarchy paths."""

from __future__ import annotations

from app.ingestion.parsers.markdown import sections_from_markdown


def test_section_path_builds_legal_hierarchy() -> None:
    md = (
        "# Quy tắc\n\n"
        "## Chương II: Phí bảo hiểm\n\n"
        "### Điều 5: Nguyên tắc tính phí\n\n"
        "Nội dung của Điều 5.\n"
    )
    sections = sections_from_markdown(md, doc_title="Quy tắc")
    dieu5 = [s for s in sections if "Nội dung của Điều 5." in s.text]
    assert len(dieu5) == 1
    assert "Chương II > Điều 5" in dieu5[0].section_path


def test_heading_pop_resets_deeper_levels() -> None:
    md = (
        "## Chương I: A\n\n### Điều 1: x\n\nND1.\n\n"
        "## Chương II: B\n\n### Điều 2: y\n\nND2.\n"
    )
    sections = sections_from_markdown(md)
    nd2 = [s for s in sections if "ND2." in s.text][0]
    # Điều 2 lives under Chương II, not Chương I — deeper level was popped.
    assert nd2.section_path == "Chương II > Điều 2"


def test_empty_sections_dropped() -> None:
    md = "# Title\n\n## Chương I: A\n\n## Chương II: B\n\nCó nội dung.\n"
    sections = sections_from_markdown(md, doc_title="Title")
    assert all(s.text.strip() for s in sections)
    assert any("Có nội dung." in s.text for s in sections)
