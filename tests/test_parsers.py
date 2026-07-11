"""Parser tests — Markdown sectionizer, Vietnamese hierarchy paths, XLSX tables."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.ingestion.parsers.glossary_parser import parse_glossary
from app.ingestion.parsers.markdown import sections_from_markdown
from app.ingestion.parsers.xlsx_parser import parse_xlsx
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


def _write_xlsx_fixture(tmp_path: Path) -> Path:
    """Two-sheet workbook: VN text, dates, big ints, a merged cell, a pipe."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Chi trả"
    ws.append(["Mã hồ sơ", "Ngày nộp", "Số tiền (VND)", "Ghi chú"])
    ws.append(["HS-01", date(2025, 1, 14), 500_000_000, "tử vong | tai nạn"])
    ws.append(["HS-02", date(2025, 2, 3), 40_000_000.0, None])
    # Merged across the last two data rows: both must show the anchor value.
    ws.append(["HS-03", date(2025, 3, 7), 120_000_000, "gộp"])
    ws.merge_cells(start_row=4, start_column=4, end_row=5, end_column=4)
    ws.cell(row=5, column=1, value="HS-04")
    wb.create_sheet("Trống")  # empty sheet must be skipped
    summary = wb.create_sheet("Tổng hợp")
    summary.append(["Chỉ tiêu", "Giá trị"])
    summary.append(["Tổng chi trả", 660_000_000])
    p = tmp_path / "chi_tra_test.xlsx"
    wb.save(p)
    return p


def test_parse_xlsx_one_markdown_table_per_sheet(tmp_path: Path) -> None:
    doc = parse_xlsx(_write_xlsx_fixture(tmp_path))
    assert doc.doc_type == DocType.SPREADSHEET
    # No workbook Title property in the fixture -> filename fallback.
    assert doc.doc_title == "chi tra test"
    # Empty sheet skipped; the two populated sheets become sections.
    assert [s.section_path for s in doc.sections] == ["Chi trả", "Tổng hợp"]
    table = doc.sections[0].text
    lines = table.split("\n")
    assert lines[0].startswith("| Mã hồ sơ |")
    assert set(lines[1].replace("|", "").split()) == {"---"}
    # Every line is a table row — chunking's never-split-mid-row rule applies.
    assert all(ln.startswith("|") and ln.endswith("|") for ln in lines)


def test_parse_xlsx_formats_values(tmp_path: Path) -> None:
    table = parse_xlsx(_write_xlsx_fixture(tmp_path)).sections[0].text
    assert "2025-01-14" in table  # dates as ISO, not datetime repr
    assert "40000000" in table and "40000000.0" not in table  # int-valued floats
    assert "tử vong \\| tai nạn" in table  # pipes escaped, grid intact


def test_parse_xlsx_forward_fills_merged_cells(tmp_path: Path) -> None:
    table = parse_xlsx(_write_xlsx_fixture(tmp_path)).sections[0].text
    hs04_row = next(ln for ln in table.split("\n") if "HS-04" in ln)
    assert "gộp" in hs04_row  # merged cell filled from its anchor


def test_router_dispatches_xlsx_and_rejects_legacy_xls(tmp_path: Path) -> None:
    doc = route_to_parser(_write_xlsx_fixture(tmp_path))
    assert doc.doc_type == DocType.SPREADSHEET
    xls = tmp_path / "old.xls"
    xls.write_bytes(b"")
    with pytest.raises(NotImplementedError, match="xlsx"):
        route_to_parser(xls)
