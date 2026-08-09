"""app/text_utils.py::fold_text — MAINT1 (2026-08-05 audit).

Extracted from 5 byte-for-byte-identical copies across product_scope.py,
metric_guard.py, coverage.py, coverage_gate.py, and metric_hints.py. These
cases mirror what each of those callers actually relies on.
"""

from __future__ import annotations

from app.text_utils import fold_text, sanitize_model_output


def test_strips_diacritics_and_lowercases() -> None:
    assert fold_text("Điều khoản") == "dieu khoan"


def test_dd_stroke_becomes_plain_d() -> None:
    # unicodedata.combining() alone doesn't touch đ/Đ (not a combining mark),
    # so the explicit replace is load-bearing, not redundant.
    assert fold_text("đ") == "d"
    assert fold_text("Đ") == "d"


def test_idempotent_on_already_folded_text() -> None:
    assert fold_text("dieu khoan") == "dieu khoan"


def test_leaves_digits_and_punctuation_alone() -> None:
    assert fold_text("Điều 5, Khoản 2%") == "dieu 5, khoan 2%"


def test_folds_terms_from_every_former_call_site() -> None:
    # One phrase representative of each of the 5 consolidated guards' domain
    # vocabulary (product names, benefit/exclusion markers, metric labels).
    assert fold_text("Quy tắc, Điều khoản") == "quy tac, dieu khoan"  # product_scope
    assert fold_text("có được chi trả") == "co duoc chi tra"  # metric_guard/coverage
    assert fold_text("Loại trừ trách nhiệm") == "loai tru trach nhiem"  # coverage_gate
    assert fold_text("lãi suất cam kết") == "lai suat cam ket"  # metric_hints


def test_sanitize_model_output_replaces_known_cjk_and_strips_runs() -> None:
    assert "tham gia" in sanitize_model_output("người投保 có thể", strip_edges=True)
    assert "投保" not in sanitize_model_output("người投保 có thể", strip_edges=True)
    assert sanitize_model_output("纯中文", strip_edges=True) == ""


def test_sanitize_model_output_replaces_and_strips_cjk() -> None:
    assert (
        sanitize_model_output("người投保 mua bảo hiểm", strip_edges=True)
        == "người tham gia mua bảo hiểm"
    )
    assert sanitize_model_output("bình thường", strip_edges=True) == "bình thường"


def test_sanitize_model_output_preserves_leading_space_on_stream_chunks() -> None:
    """Stream tokens often arrive as ' thuần' — must not strip the word boundary."""
    assert sanitize_model_output(" thuần") == " thuần"
    assert sanitize_model_output("Phí") + sanitize_model_output(" thuần") == "Phí thuần"
