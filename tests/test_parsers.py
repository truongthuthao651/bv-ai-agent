"""Parser tests — Markdown sectionizer + Vietnamese hierarchy paths."""

from __future__ import annotations

from pathlib import Path

from app.ingestion.parsers.glossary_parser import parse_glossary
from app.ingestion.parsers.markdown import sections_from_markdown
from app.ingestion.router import route_to_parser
from app.models.schemas import DocType


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


def _write_glossary_fixture(tmp_path: Path) -> Path:
    p = tmp_path / "thuat_ngu.yaml"
    p.write_text(
        "- term: \"phí thuần\"\n"
        "  synonyms: [\"net premium\"]\n"
        "  symbol: \"P\"\n"
        "  definition: \"Phần phí bảo hiểm chỉ đủ để trang trải quyền lợi.\"\n",
        encoding="utf-8",
    )
    return p


def test_parse_glossary_one_section_per_term(tmp_path: Path) -> None:
    doc = parse_glossary(_write_glossary_fixture(tmp_path))
    assert doc.doc_type == DocType.GLOSSARY
    assert len(doc.sections) == 1
    section = doc.sections[0]
    assert section.section_path == "phí thuần"
    assert "$P$" in section.text
    assert "net premium" in section.text


def test_router_dispatches_yaml_to_glossary_parser(tmp_path: Path) -> None:
    doc = route_to_parser(_write_glossary_fixture(tmp_path))
    assert doc.doc_type == DocType.GLOSSARY
    assert doc.sections[0].section_path == "phí thuần"
