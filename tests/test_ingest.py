"""Ingestion endpoint safety + document lifecycle.

Upload-name sanitizing, stable doc-id derivation, and the DELETE endpoint
(with the indexer faked) — no Qdrant or embedding model needed.
"""

from __future__ import annotations

from app.api.ingest import _safe_filename, doc_id_for_filename


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


# --------------------------------------------------------------------------- #
# Stable doc ids (re-upload replaces; eval maps source_doc -> doc_id)
# --------------------------------------------------------------------------- #


def test_doc_id_for_filename_is_stable_and_distinct() -> None:
    a1 = doc_id_for_filename("quy_tac_tu_ky_an_tam.md")
    a2 = doc_id_for_filename("quy_tac_tu_ky_an_tam.md")
    b = doc_id_for_filename("thuat_ngu.yaml")
    assert a1 == a2
    assert a1 != b


# --------------------------------------------------------------------------- #
# DELETE /documents/{doc_id} (indexer faked; no Qdrant)
# --------------------------------------------------------------------------- #


def _client():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_delete_document_removes_and_reports_chunks(monkeypatch) -> None:
    from app.ingestion import indexer

    deleted: list[str] = []
    monkeypatch.setattr(indexer, "count_document_points", lambda doc_id: 7)
    monkeypatch.setattr(indexer, "delete_document", deleted.append)

    resp = _client().delete("/documents/abc-123")
    assert resp.status_code == 200
    assert resp.json() == {"doc_id": "abc-123", "deleted_chunks": 7}
    assert deleted == ["abc-123"]


def test_delete_unknown_document_is_404_and_deletes_nothing(monkeypatch) -> None:
    from app.ingestion import indexer

    deleted: list[str] = []
    monkeypatch.setattr(indexer, "count_document_points", lambda doc_id: 0)
    monkeypatch.setattr(indexer, "delete_document", deleted.append)

    resp = _client().delete("/documents/khong-ton-tai")
    assert resp.status_code == 404
    assert deleted == []
