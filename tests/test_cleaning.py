"""Cleaning tests — NFC normalization and running header/footer stripping."""

from __future__ import annotations

import unicodedata

from app.ingestion.cleaning import normalize_text, strip_headers_footers


def test_normalize_text_composes_nfc_and_line_endings() -> None:
    decomposed = unicodedata.normalize("NFD", "Bảo hiểm nhân thọ")
    out = normalize_text(decomposed + "\r\nx\r\n\n\n\ny")
    assert "Bảo hiểm nhân thọ" in out
    assert out == unicodedata.normalize("NFC", out)
    assert "\r" not in out
    assert "\n\n\n" not in out  # 3+ blank lines collapsed


def test_strip_page_number_lines() -> None:
    text = "Nội dung A.\n- 12 -\nTrang 3\n3/10\nNội dung B."
    out = strip_headers_footers(text)
    assert "Nội dung A." in out and "Nội dung B." in out
    for junk in ("- 12 -", "Trang 3", "3/10"):
        assert junk not in out


def test_strip_repeated_running_footer() -> None:
    footer = "Công ty ABC — Lưu hành nội bộ"
    text = "\n".join(["Đoạn một.", footer, "Đoạn hai.", footer, "Đoạn ba.", footer])
    out = strip_headers_footers(text, repeated_min=3)
    assert footer not in out
    assert all(p in out for p in ("Đoạn một.", "Đoạn hai.", "Đoạn ba."))


def test_infrequent_line_kept() -> None:
    line = "Điều khoản quan trọng."
    text = "\n".join([line, "Khác.", line])
    assert line in strip_headers_footers(text, repeated_min=3)


def test_headings_tables_and_math_never_stripped() -> None:
    text = "\n".join(
        ["## Điều 1", "| a | b |", "$$P = 1$$"] * 4  # repeated >= 3 times each
    )
    out = strip_headers_footers(text, repeated_min=3)
    assert "## Điều 1" in out
    assert "| a | b |" in out
    assert "$$P = 1$$" in out
