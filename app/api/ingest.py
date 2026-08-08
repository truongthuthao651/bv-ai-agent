"""Ingestion endpoints.

``POST /ingest`` runs one uploaded file through the pipeline
(parse -> clean -> chunk -> enrich -> index) and ``GET /documents`` lists what is
currently indexed. Heavy work runs in a threadpool so it doesn't block the event
loop. See the ingestion modules and the insurance-rag-pipeline skill (sections 1-5).
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

from app import auth
from app.api import docview
from app.config.settings import settings
from app.ingestion import indexer
from app.ingestion.chunking import chunk_document
from app.ingestion.enrichment import enrich_chunks
from app.ingestion.router import route_to_parser
from app.models.schemas import (
    DocType,
    DocumentDeleteResponse,
    DocumentInfo,
    DocumentUpdateRequest,
    IngestResponse,
)

router = APIRouter(tags=["ingest"])

# Read/write granularity for _write_upload_capped. Small enough to reject an
# oversized upload without buffering it all in memory first.
_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB

# Stable doc_id per filename so re-uploading the same file replaces its points.
_DOC_NAMESPACE = uuid.UUID("6f4a1d9e-0b2c-4e77-9a1b-000000000002")


def doc_id_for_filename(filename: str) -> str:
    """Deterministic doc_id for an uploaded filename.

    Public because the eval harness maps golden-set ``source_doc`` filenames to
    the doc_ids it should find in retrieval results.
    """
    return str(uuid.uuid5(_DOC_NAMESPACE, filename))


def _validate_department(department: str | None) -> str | None:
    """Normalize/validate a department against ``settings.departments``.

    Empty/whitespace -> None (no department). A non-empty value not in the
    allowed set is a 400 — the admin UI only offers the configured list, so this
    only trips on hand-crafted requests.
    """
    if department is None:
        return None
    department = department.strip()
    if not department:
        return None
    if department not in settings.departments:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Phòng ban không hợp lệ: «{department}». "
                f"Chọn một trong: {', '.join(settings.departments)}."
            ),
        )
    return department


def _validate_source_url(source_url: str | None) -> str | None:
    """Normalize/validate the public URL a knowledge-pack document came from.

    Empty/whitespace -> None. Only ``http(s)`` is accepted: the value is
    rendered as a Markdown citation link, so a ``javascript:``/``data:`` URL
    would be an injection vector, and any other scheme could not be a public
    source anyway. The app NEVER fetches this URL — it is provenance only, so
    accepting it does not put the deployment back on the network.
    """
    if source_url is None:
        return None
    source_url = source_url.strip()
    if not source_url:
        return None
    if not re.match(r"^https?://[^\s<>\"')]+$", source_url, flags=re.IGNORECASE):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nguồn URL không hợp lệ: «{source_url}». "
                "Chỉ chấp nhận địa chỉ bắt đầu bằng http:// hoặc https://."
            ),
        )
    return source_url


def _safe_filename(name: str | None) -> str:
    """Reduce an uploaded filename to a safe basename.

    The client-supplied name is untrusted: a value like ``../../etc/passwd`` (or
    an absolute path) would otherwise let the write escape ``data/uploads``. Take
    only the final path component and reject the traversal specials, falling back
    to a fixed name so ingestion still proceeds.
    """
    base = PurePosixPath((name or "").replace("\\", "/")).name
    if not base or base in {".", ".."}:
        return "upload"
    return base


# Formats where the product name commonly lives only on cover artwork, so a
# title auto-taken from the first heading may silently miss it (unlike XLSX /
# glossary, whose titles come from the file/sheet name the user controls).
_TITLE_WARN_EXTS = {".pdf", ".docx"}


def _title_warning(doc, ext: str, override_given: bool) -> str | None:
    """Advisory when the auto-title came purely from the document's own heading.

    The title is prepended to every chunk's embed_text and rerank text, so a
    title missing the product name buries that product's benefit sections for
    product-scoped queries (see the doc-title/retrieval note). We can't tell
    whether the heading already contains the product name, so this is a soft
    nudge, not an error — and it's skipped entirely when the user supplied an
    explicit title or the filename already contributed extra words.
    """
    if override_given or ext.lower() not in _TITLE_WARN_EXTS:
        return None
    if doc.title_source != "heading":  # merged-with-filename or non-heading title
        return None
    return (
        f"Tên tài liệu được tự động trích từ tiêu đề trong file: "
        f"«{doc.doc_title}». Nếu tên này THIẾU tên sản phẩm (ví dụ brochure chỉ "
        f"ghi tên sản phẩm ở trang bìa), hãy nạp lại và điền đầy đủ tên vào ô "
        f"«Tên tài liệu» để trợ lý tìm đúng tài liệu khi hỏi theo tên sản phẩm."
    )


async def _write_upload_capped(file: UploadFile, dest: Path) -> None:
    """Stream ``file`` to ``dest``, rejecting once it exceeds ``MAX_UPLOAD_MB``.

    Reads in fixed-size chunks instead of ``await file.read()`` in one shot
    (the previous behavior), so an oversized upload is rejected mid-stream
    rather than only after the whole thing is already buffered in memory
    (SEC4). The partial file is removed before raising, so a rejected upload
    never leaves anything on disk.
    """
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    too_large = False
    with dest.open("wb") as out:
        while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
            written += len(chunk)
            if written > max_bytes:
                too_large = True
                break
            out.write(chunk)
    if too_large:
        dest.unlink(missing_ok=True)
        raise HTTPException(
            status_code=413,
            detail=(f"Tệp vượt quá giới hạn {settings.max_upload_mb} MB cho phép."),
        )


def _run_pipeline(
    path: Path,
    doc_type: DocType | None,
    doc_title: str | None = None,
    department: str | None = None,
    source_url: str | None = None,
) -> IngestResponse:
    """Synchronous parse -> clean -> chunk -> enrich -> index for one file."""
    doc = route_to_parser(path, doc_type=doc_type)
    doc.department = department  # None keeps it unset; carried into every chunk
    doc.source_url = source_url  # public original, for knowledge-pack citations
    override_given = bool(doc_title and doc_title.strip())
    if override_given:
        # Manual override: real-world PDFs often carry a generic first heading
        # ("SẢN PHẨM BẢO HIỂM LIÊN KẾT CHUNG") while the product name lives in
        # cover artwork. The title feeds embed_text prefixes, reranking, and
        # citations, so a precise one measurably improves retrieval.
        doc.doc_title = unicodedata.normalize("NFC", doc_title.strip())
    # NFC-normalize section text (idempotent; parsers already normalize).
    for section in doc.sections:
        section.text = unicodedata.normalize("NFC", section.text)

    doc_id = doc_id_for_filename(path.name)
    chunks = chunk_document(
        doc,
        doc_id,
        count_tokens=indexer.count_tokens,
        max_tokens=settings.chunk_max_tokens,
        overlap_pct=settings.chunk_overlap_pct,
        child_max_tokens=(
            settings.chunk_child_max_tokens
            if settings.parent_child_chunking_enabled
            else None
        ),
    )
    chunks = enrich_chunks(chunks)
    n_points = indexer.index_chunks(chunks)
    return IngestResponse(
        doc_id=doc_id,
        doc_title=doc.doc_title,
        doc_type=doc.doc_type,
        n_chunks=n_points,
        n_figures=len(doc.figures),
        title_warning=_title_warning(doc, path.suffix, override_given),
    )


@router.post(
    "/ingest", response_model=IngestResponse, dependencies=[Depends(auth.require_admin)]
)
async def ingest_file(
    file: UploadFile = File(...),
    doc_type: DocType | None = Form(default=None),
    doc_title: str | None = Form(default=None),
    department: str | None = Form(default=None),
    source_url: str | None = Form(default=None),
) -> IngestResponse:
    """Ingest a single document (Markdown/DOCX/XLSX/glossary YAML).

    ``source_url`` marks the file as knowledge-pack material downloaded from a
    public page (law, circular, public brochure): citations then link to that
    public original instead of the internal viewer.
    """
    department = _validate_department(department)
    source_url = _validate_source_url(source_url)
    filename = _safe_filename(file.filename)
    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / filename
    await _write_upload_capped(file, dest)

    try:
        return await run_in_threadpool(
            _run_pipeline, dest, doc_type, doc_title, department, source_url
        )
    except (NotImplementedError, ValueError) as exc:
        # SEC4: previously left the uploaded file orphaned on disk, unindexed,
        # on every parse-format failure.
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except Exception:
        # Anything else (a corrupt file, an OOM in enrichment, ...) must not
        # leave the file behind either — re-raise unchanged so it's still
        # reported the same way it would have been before this change.
        dest.unlink(missing_ok=True)
        raise


@router.get(
    "/documents",
    response_model=list[DocumentInfo],
    dependencies=[Depends(auth.require_admin)],
)
async def list_documents() -> list[DocumentInfo]:
    """List documents currently indexed in Qdrant. Admin-only: this is
    admin-console data, not something the chat UI's employee accounts need —
    /chat's citation links resolve via the /documents/{id}/view and /file
    routes instead, which require only a signed-in session (any role), not
    admin (see app.auth.PUBLIC_PREFIXES's SEC-A note)."""
    return await run_in_threadpool(indexer.list_documents)


# Source formats a browser renders inline (scroll/view without downloading).
# For these the viewer serves the original file; other types (and documents
# with no backing upload) are rebuilt from indexed chunks by docview.
_INLINE_VIEW_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _source_path_for(doc_id: str) -> Path | None:
    """Existing uploads-dir path of a document's source file, or None.

    Prefer the ``source_filename`` tracked in the Qdrant payload. Documents
    ingested before that field was tracked have no such payload, so fall back to
    a deterministic reverse-map: ``doc_id == uuid5(_DOC_NAMESPACE, filename)``,
    so any upload whose recomputed doc_id matches is this document's original
    file. This keeps citation links resolving to the real uploaded document
    (not the chunk-reconstructed rendering) even for older ingests.
    """
    uploads = settings.data_dir / "uploads"

    filename = indexer.get_document_source_filename(doc_id)
    if filename:
        # filename is a stored basename (already sanitized by _safe_filename at
        # upload time); re-sanitize defensively so a corrupted payload can't
        # escape the uploads dir.
        path = uploads / _safe_filename(filename)
        if path.is_file():
            return path

    if uploads.is_dir():
        for candidate in sorted(uploads.iterdir()):
            if candidate.is_file() and doc_id_for_filename(candidate.name) == doc_id:
                return candidate
    return None


@router.get("/documents/{doc_id}/file")
async def get_document_file(doc_id: str) -> FileResponse:
    """Serve the originally uploaded file for a document, rendered inline.

    ``content_disposition_type="inline"`` lets the browser display the file
    (PDFs scroll natively) instead of downloading it. 404 covers both "no such
    doc_id" and "doc has no backing upload" (e.g. a glossary entry) identically.
    Requires any signed-in session (not admin-only) — enforced by
    ``admin_session_gate`` in app/main.py, since this route is no longer in
    ``auth.PUBLIC_PREFIXES`` (SEC-A: it used to have no session check at all).
    """
    path = await run_in_threadpool(_source_path_for, doc_id)
    if path is None:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tệp nguồn cho tài liệu này."
        )
    return FileResponse(path, filename=path.name, content_disposition_type="inline")


def _render_view(doc_id: str, highlight_section: str | None) -> str | None:
    """Build the HTML viewer page for a document, or None if it isn't indexed.

    PDFs/images are left to ``/file`` (the caller redirects); everything else is
    reconstructed from the document's chunks so the citation link always
    resolves to a scrollable, readable page — even without a backing upload.
    """
    chunks = indexer.get_document_chunks(doc_id)
    if not chunks:
        return None
    doc_title, sections = docview.reconstruct_sections(chunks)
    return docview.render_page(
        doc_title,
        sections,
        doc_id=doc_id,
        highlight_section=highlight_section,
        has_source_file=_source_path_for(doc_id) is not None,
    )


@router.get("/documents/{doc_id}/view", response_class=HTMLResponse)
async def view_document(
    doc_id: str, section: str | None = None, page: int | None = None
):
    """Scrollable rendered view of a source document (citation link target).

    For PDFs/images with a backing upload, redirect to ``/file`` so the browser
    renders the real document natively; otherwise rebuild a readable HTML page
    from the indexed chunks. ``section`` deep-links to a cited section; ``page``
    scrolls a native PDF straight to the cited page via the ``#page=N`` fragment
    that browser PDF viewers honor (like ChatGPT/Gemini source previews).
    """
    path = await run_in_threadpool(_source_path_for, doc_id)
    if path is not None and path.suffix.lower() in _INLINE_VIEW_EXTS:
        url = f"/documents/{doc_id}/file"
        if page is not None and page > 0 and path.suffix.lower() == ".pdf":
            url += f"#page={int(page)}"
        return RedirectResponse(url=url, status_code=307)

    rendered = await run_in_threadpool(_render_view, doc_id, section)
    if rendered is None:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tài liệu với doc_id này."
        )
    return HTMLResponse(rendered)


@router.delete(
    "/documents/{doc_id}",
    response_model=DocumentDeleteResponse,
    dependencies=[Depends(auth.require_admin)],
)
async def delete_document(doc_id: str) -> DocumentDeleteResponse:
    """Remove all indexed chunks of one document (by ``doc_id``)."""
    n_chunks = await run_in_threadpool(indexer.count_document_points, doc_id)
    if n_chunks == 0:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tài liệu với doc_id này."
        )
    await run_in_threadpool(indexer.delete_document, doc_id)
    return DocumentDeleteResponse(doc_id=doc_id, deleted_chunks=n_chunks)


def _document_info(doc_id: str) -> DocumentInfo | None:
    """Fresh ``DocumentInfo`` for one document after an edit, or None if gone."""
    for info in indexer.list_documents():
        if info.doc_id == doc_id:
            return info
    return None


def _apply_update(doc_id: str, req: DocumentUpdateRequest) -> DocumentInfo:
    """Apply a metadata update (renames re-ingest; type/dept are payload-only).

    A ``doc_title`` change re-ingests the document from its source file so the
    new title flows into embeddings + reranking (it's part of ``embed_text``);
    when there is no source file to re-ingest from, it degrades to a
    metadata-only title change (retrieval stays keyed to the old embedded title
    until the file is re-uploaded). ``doc_type``/``department``/``source_url``
    are always a metadata-only ``set_payload`` — none of them is embedded.
    """
    meta = indexer.get_document_meta(doc_id)
    if meta is None:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tài liệu với doc_id này."
        )

    fields = req.model_fields_set
    new_type = req.doc_type if "doc_type" in fields and req.doc_type else None
    set_department = "department" in fields
    new_dept = _validate_department(req.department) if set_department else None
    set_source_url = "source_url" in fields
    new_source_url = _validate_source_url(req.source_url) if set_source_url else None

    new_title = None
    if "doc_title" in fields and req.doc_title and req.doc_title.strip():
        new_title = unicodedata.normalize("NFC", req.doc_title.strip())
    title_changed = new_title is not None and new_title != meta["doc_title"]

    if title_changed:
        source = _source_path_for(doc_id)
        if source is not None:
            # Full re-ingest with the new title (and any type/department change),
            # preserving the current values for whatever the caller didn't touch.
            eff_type = new_type or DocType(meta["doc_type"])
            eff_dept = new_dept if set_department else meta["department"]
            # .get: documents indexed before source_url existed carry no such key.
            eff_url = new_source_url if set_source_url else meta.get("source_url")
            _run_pipeline(source, eff_type, new_title, eff_dept, eff_url)
        else:
            indexer.set_document_metadata(
                doc_id,
                doc_title=new_title,
                doc_type=(new_type.value if new_type else None),
                department=new_dept,
                set_department=set_department,
                source_url=new_source_url,
                set_source_url=set_source_url,
            )
    else:
        indexer.set_document_metadata(
            doc_id,
            doc_type=(new_type.value if new_type else None),
            department=new_dept,
            set_department=set_department,
            source_url=new_source_url,
            set_source_url=set_source_url,
        )

    info = _document_info(doc_id)
    if info is None:  # pragma: no cover - would mean the doc vanished mid-update
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tài liệu với doc_id này."
        )
    return info


@router.patch(
    "/documents/{doc_id}",
    response_model=DocumentInfo,
    dependencies=[Depends(auth.require_admin)],
)
async def update_document(doc_id: str, request: DocumentUpdateRequest) -> DocumentInfo:
    """Edit a document's title, type, and/or department.

    Renaming re-ingests from the source file (slow — it re-parses and re-embeds)
    so retrieval follows the new name; changing only type/department is an
    instant metadata update.
    """
    return await run_in_threadpool(_apply_update, doc_id, request)
