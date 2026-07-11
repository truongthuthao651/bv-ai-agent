"""Ingestion endpoint safety: uploaded filenames are untrusted.

Pure-function tests for the upload-name sanitizer — no FastAPI client, Qdrant,
or embedding model needed.
"""

from __future__ import annotations

from app.api.ingest import _safe_filename


def test_safe_filename_strips_posix_traversal() -> None:
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("/etc/passwd") == "passwd"
    assert _safe_filename("data/uploads/../../secret.md") == "secret.md"


def test_safe_filename_strips_windows_traversal() -> None:
    assert _safe_filename("..\\..\\windows\\system32\\x.dll") == "x.dll"


def test_safe_filename_keeps_plain_basenames() -> None:
    assert _safe_filename("quy_tac_tu_ky_an_tam.md") == "quy_tac_tu_ky_an_tam.md"
    assert _safe_filename("Báo cáo 2026.docx") == "Báo cáo 2026.docx"


def test_safe_filename_falls_back_on_empty_or_specials() -> None:
    assert _safe_filename(None) == "upload"
    assert _safe_filename("") == "upload"
    assert _safe_filename(".") == "upload"
    assert _safe_filename("..") == "upload"
    assert _safe_filename("/") == "upload"


def test_safe_filename_never_escapes_uploads_dir() -> None:
    from pathlib import Path

    uploads = Path("/app/data/uploads")
    for hostile in ("../../etc/passwd", "/etc/passwd", "..", "..\\..\\x"):
        dest = uploads / _safe_filename(hostile)
        assert dest.parent == uploads  # write stays inside uploads/
