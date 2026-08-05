"""Ingestion endpoint safety + document lifecycle.

Upload-name sanitizing, stable doc-id derivation, and the DELETE endpoint
(with the indexer faked) — no Qdrant or embedding model needed.
"""

from __future__ import annotations

import pytest

from app.api.ingest import (
    _safe_filename,
    _source_path_for,
    _validate_department,
    doc_id_for_filename,
)
from app.models.schemas import DocType, DocumentInfo


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
# Original-file resolution (citation links serve the uploaded file, not the
# chunk-reconstructed rendering) — indexer.get_document_source_filename faked
# --------------------------------------------------------------------------- #


def test_source_path_prefers_tracked_filename(tmp_path, monkeypatch) -> None:
    from app.api import ingest
    from app.ingestion import indexer

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "quy_tac.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(ingest.settings, "data_dir", tmp_path)
    monkeypatch.setattr(
        indexer, "get_document_source_filename", lambda doc_id: "quy_tac.pdf"
    )

    assert _source_path_for("any-doc-id") == uploads / "quy_tac.pdf"


def test_source_path_falls_back_to_doc_id_reverse_map(tmp_path, monkeypatch) -> None:
    """Docs ingested before source_filename tracking have no payload filename;
    resolve them by recomputing doc_id from each upload's basename."""
    from app.api import ingest
    from app.ingestion import indexer

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "DK-R23_(trang-don).pdf").write_bytes(b"%PDF-1.4\n")
    (uploads / "other.pdf").write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(ingest.settings, "data_dir", tmp_path)
    monkeypatch.setattr(indexer, "get_document_source_filename", lambda doc_id: None)

    doc_id = doc_id_for_filename("DK-R23_(trang-don).pdf")
    assert _source_path_for(doc_id) == uploads / "DK-R23_(trang-don).pdf"


def test_source_path_none_when_no_matching_upload(tmp_path, monkeypatch) -> None:
    from app.api import ingest
    from app.ingestion import indexer

    (tmp_path / "uploads").mkdir()
    monkeypatch.setattr(ingest.settings, "data_dir", tmp_path)
    monkeypatch.setattr(indexer, "get_document_source_filename", lambda doc_id: None)

    assert _source_path_for("no-such-doc") is None


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


# --------------------------------------------------------------------------- #
# Open WebUI meta-task bypass (chat titles/tags must not run the RAG pipeline)
# --------------------------------------------------------------------------- #


def test_meta_task_detection() -> None:
    from app.api.chat import _is_meta_task

    assert _is_meta_task("### Task:\nGenerate 1-3 broad tags...")
    assert _is_meta_task("Create a concise, 3-5 word title with an emoji...")
    assert not _is_meta_task("Phí thuần là gì?")
    assert not _is_meta_task("tính net premium")


def test_meta_task_bypasses_retrieval(monkeypatch) -> None:
    import app.api.chat as chat_module
    from app.generation import generator

    def boom(*_args):  # retrieval must never run for meta-tasks
        raise AssertionError("retrieval was called for a meta-task")

    monkeypatch.setattr(chat_module, "_retrieve", boom)
    monkeypatch.setattr(generator, "generate_plain", lambda prompt: "Tiêu đề chat")

    resp = _client().post(
        "/v1/chat/completions",
        json={
            "stream": False,
            "messages": [
                {"role": "user", "content": "Create a concise, 3-5 word title ..."}
            ],
        },
    )
    assert resp.status_code == 200
    assert resp.json()["choices"][0]["message"]["content"] == "Tiêu đề chat"


# --------------------------------------------------------------------------- #
# Embedded Qdrant (QDRANT_LOCAL_PATH — the no-Docker deployment mode)
# --------------------------------------------------------------------------- #


def test_get_client_embedded_local_mode(tmp_path, monkeypatch) -> None:
    """A set QDRANT_LOCAL_PATH yields an in-process client — no server needed."""
    from app.ingestion import indexer

    monkeypatch.setattr(indexer.settings, "qdrant_local_path", str(tmp_path / "qdrant"))
    client = indexer.get_client.__wrapped__()  # bypass the lru_cache
    try:
        assert not client.collection_exists("nonexistent")
    finally:
        client.close()


# --------------------------------------------------------------------------- #
# Department validation
# --------------------------------------------------------------------------- #


def test_validate_department_accepts_known_and_normalizes_empty() -> None:
    assert _validate_department("PTSP") == "PTSP"
    assert _validate_department("  DVA  ") == "DVA"
    assert _validate_department(None) is None
    assert _validate_department("") is None
    assert _validate_department("   ") is None


def test_validate_department_rejects_unknown() -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        _validate_department("KHONG-CO")
    assert exc.value.status_code == 400


# --------------------------------------------------------------------------- #
# PATCH /documents/{doc_id} (metadata edit; rename re-ingests) — indexer faked
# --------------------------------------------------------------------------- #


def _meta(**overrides):
    base = {
        "doc_title": "Tên cũ",
        "doc_type": "policy",
        "department": None,
        "source_filename": None,
        "source_url": None,
    }
    base.update(overrides)
    return base


def test_patch_metadata_only_updates_type_and_department(monkeypatch) -> None:
    from app.ingestion import indexer

    monkeypatch.setattr(indexer, "get_document_meta", lambda doc_id: _meta())
    captured: dict = {}
    monkeypatch.setattr(
        indexer,
        "set_document_metadata",
        lambda doc_id, **kw: captured.update(kw, doc_id=doc_id),
    )
    monkeypatch.setattr(
        indexer,
        "list_documents",
        lambda: [
            DocumentInfo(
                doc_id="abc",
                doc_title="Tên cũ",
                doc_type="procedure",
                department="DP",
                n_chunks=3,
            )
        ],
    )

    resp = _client().patch(
        "/documents/abc", json={"doc_type": "procedure", "department": "DP"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["doc_type"] == "procedure"
    assert body["department"] == "DP"
    # Metadata path was taken (no title change) with department explicitly set.
    assert captured["doc_id"] == "abc"
    assert captured["doc_type"] == "procedure"
    assert captured["department"] == "DP"
    assert captured["set_department"] is True


def test_patch_rename_reingests_from_source(monkeypatch, tmp_path) -> None:
    from app.api import ingest
    from app.ingestion import indexer

    monkeypatch.setattr(
        indexer,
        "get_document_meta",
        lambda doc_id: _meta(
            doc_type="policy",
            department="PTSP",
            source_url="https://example.gov.vn/luat",
        ),
    )
    src = tmp_path / "f.md"
    src.write_text("x")
    monkeypatch.setattr(ingest, "_source_path_for", lambda doc_id: src)

    called: dict = {}

    def fake_pipeline(path, doc_type, doc_title, department, source_url=None):
        called.update(
            path=path,
            doc_type=doc_type,
            doc_title=doc_title,
            department=department,
            source_url=source_url,
        )

    monkeypatch.setattr(ingest, "_run_pipeline", fake_pipeline)
    monkeypatch.setattr(
        indexer,
        "list_documents",
        lambda: [
            DocumentInfo(
                doc_id="abc",
                doc_title="Tên mới",
                doc_type="policy",
                department="PTSP",
                n_chunks=5,
            )
        ],
    )

    resp = _client().patch("/documents/abc", json={"doc_title": "Tên mới"})
    assert resp.status_code == 200
    # Rename re-ingested from the source file, preserving every field the
    # caller didn't touch — including the knowledge-pack source URL, which
    # would otherwise be silently dropped and break that document's citations.
    assert called["path"] == src
    assert called["doc_title"] == "Tên mới"
    assert called["doc_type"] == DocType.POLICY
    assert called["department"] == "PTSP"
    assert called["source_url"] == "https://example.gov.vn/luat"


def test_patch_unknown_document_is_404(monkeypatch) -> None:
    from app.ingestion import indexer

    monkeypatch.setattr(indexer, "get_document_meta", lambda doc_id: None)
    resp = _client().patch("/documents/khong-ton-tai", json={"doc_type": "form"})
    assert resp.status_code == 404


def test_patch_invalid_department_is_400(monkeypatch) -> None:
    from app.ingestion import indexer

    monkeypatch.setattr(indexer, "get_document_meta", lambda doc_id: _meta())
    resp = _client().patch("/documents/abc", json={"department": "KHONG-CO"})
    assert resp.status_code == 400


# --------------------------------------------------------------------------- #
# SEC4 (2026-08-05 audit): upload size cap + no orphaned files on failure
# --------------------------------------------------------------------------- #


def test_oversized_upload_is_rejected_with_413_and_leaves_no_file(
    tmp_path, monkeypatch
) -> None:
    from app.api import ingest as ingest_module

    monkeypatch.setattr(ingest_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(ingest_module.settings, "max_upload_mb", 1)

    oversized = b"x" * (2 * 1024 * 1024)  # 2 MiB > the 1 MiB cap
    resp = _client().post(
        "/ingest",
        files={"file": ("large.md", oversized, "text/markdown")},
    )
    assert resp.status_code == 413
    assert "1 MB" in resp.json()["detail"]
    assert list((tmp_path / "uploads").iterdir()) == []  # nothing orphaned


def test_upload_within_cap_is_written_and_reaches_the_pipeline(
    tmp_path, monkeypatch
) -> None:
    from app.api import ingest as ingest_module
    from app.models.schemas import DocType, IngestResponse

    monkeypatch.setattr(ingest_module.settings, "data_dir", tmp_path)
    monkeypatch.setattr(ingest_module.settings, "max_upload_mb", 1)

    seen_paths: list[str] = []

    def fake_run_pipeline(path, doc_type, doc_title, department, source_url):
        seen_paths.append(path.read_bytes().decode())
        return IngestResponse(
            doc_id="d1", doc_title="T", doc_type=DocType.OTHER, n_chunks=1
        )

    monkeypatch.setattr(ingest_module, "_run_pipeline", fake_run_pipeline)

    resp = _client().post(
        "/ingest",
        files={"file": ("small.md", b"noi dung nho", "text/markdown")},
    )
    assert resp.status_code == 200
    assert seen_paths == ["noi dung nho"]
    # A successful ingest keeps the uploaded file (needed for citation links).
    assert (tmp_path / "uploads" / "small.md").exists()


def test_parse_failure_cleans_up_the_uploaded_file(tmp_path, monkeypatch) -> None:
    # SEC4: previously the file stayed on disk forever, unindexed, on every
    # parse-format failure (NotImplementedError/ValueError from _run_pipeline).
    from app.api import ingest as ingest_module

    monkeypatch.setattr(ingest_module.settings, "data_dir", tmp_path)

    def boom(path, doc_type, doc_title, department, source_url):
        raise ValueError("định dạng không hỗ trợ")

    monkeypatch.setattr(ingest_module, "_run_pipeline", boom)

    resp = _client().post(
        "/ingest",
        files={"file": ("bad.xyz", b"noi dung", "application/octet-stream")},
    )
    assert resp.status_code == 415
    assert list((tmp_path / "uploads").iterdir()) == []


def test_unexpected_pipeline_error_also_cleans_up_the_uploaded_file(
    tmp_path, monkeypatch
) -> None:
    # SEC4: cleanup must not be scoped to only the two expected exception
    # types -- an OOM/corrupt-file surprise must not orphan the file either.
    from app.api import ingest as ingest_module

    monkeypatch.setattr(ingest_module.settings, "data_dir", tmp_path)

    def boom(path, doc_type, doc_title, department, source_url):
        raise RuntimeError("out of memory")

    monkeypatch.setattr(ingest_module, "_run_pipeline", boom)

    from fastapi.testclient import TestClient

    from app.main import app

    # raise_server_exceptions=False: an unhandled RuntimeError is exactly what
    # this test is exercising -- assert the resulting 500, not pytest's own
    # propagation of it, and that cleanup ran before FastAPI's error handling.
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        "/ingest",
        files={"file": ("bad.md", b"noi dung", "text/markdown")},
    )
    assert resp.status_code == 500
    assert list((tmp_path / "uploads").iterdir()) == []
