"""Ingestion endpoints.

``POST /ingest`` runs one uploaded file through the pipeline
(parse -> clean -> chunk -> enrich -> index) and ``GET /documents`` lists what is
currently indexed. Heavy work runs in a threadpool so it doesn't block the event
loop. See the ingestion modules and the insurance-rag-pipeline skill (sections 1-5).
"""

from __future__ import annotations

import unicodedata
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

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
    IngestResponse,
)

router = APIRouter(tags=["ingest"])

# Stable doc_id per filename so re-uploading the same file replaces its points.
_DOC_NAMESPACE = uuid.UUID("6f4a1d9e-0b2c-4e77-9a1b-000000000002")


def doc_id_for_filename(filename: str) -> str:
    """Deterministic doc_id for an uploaded filename.

    Public because the eval harness maps golden-set ``source_doc`` filenames to
    the doc_ids it should find in retrieval results.
    """
    return str(uuid.uuid5(_DOC_NAMESPACE, filename))


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


def _run_pipeline(
    path: Path, doc_type: DocType | None, doc_title: str | None = None
) -> IngestResponse:
    """Synchronous parse -> clean -> chunk -> enrich -> index for one file."""
    doc = route_to_parser(path, doc_type=doc_type)
    if doc_title:
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
    )
    chunks = enrich_chunks(chunks)
    n_points = indexer.index_chunks(chunks)
    return IngestResponse(
        doc_id=doc_id,
        doc_title=doc.doc_title,
        doc_type=doc.doc_type,
        n_chunks=n_points,
        n_figures=len(doc.figures),
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    doc_type: DocType | None = Form(default=None),
    doc_title: str | None = Form(default=None),
) -> IngestResponse:
    """Ingest a single document (Markdown/DOCX/XLSX/glossary YAML)."""
    filename = _safe_filename(file.filename)
    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / filename
    dest.write_bytes(await file.read())

    try:
        return await run_in_threadpool(_run_pipeline, dest, doc_type, doc_title)
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents() -> list[DocumentInfo]:
    """List documents currently indexed in Qdrant."""
    return await run_in_threadpool(indexer.list_documents)


# Source formats a browser renders inline (scroll/view without downloading).
# For these the viewer serves the original file; other types (and documents
# with no backing upload) are rebuilt from indexed chunks by docview.
_INLINE_VIEW_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _source_path_for(doc_id: str) -> Path | None:
    """Existing uploads-dir path of a document's source file, or None."""
    filename = indexer.get_document_source_filename(doc_id)
    if not filename:
        return None
    # filename is a stored basename (already sanitized by _safe_filename at
    # upload time); re-sanitize defensively so a corrupted payload can't escape
    # the uploads dir.
    path = settings.data_dir / "uploads" / _safe_filename(filename)
    return path if path.is_file() else None


@router.get("/documents/{doc_id}/file")
async def get_document_file(doc_id: str) -> FileResponse:
    """Serve the originally uploaded file for a document, rendered inline.

    ``content_disposition_type="inline"`` lets the browser display the file
    (PDFs scroll natively) instead of downloading it. 404 covers both "no such
    doc_id" and "doc has no backing upload" (e.g. a glossary entry) identically.
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
async def view_document(doc_id: str, section: str | None = None):
    """Scrollable rendered view of a source document (citation link target).

    For PDFs/images with a backing upload, redirect to ``/file`` so the browser
    renders the real document natively; otherwise rebuild a readable HTML page
    from the indexed chunks. ``section`` deep-links to a cited section.
    """
    path = await run_in_threadpool(_source_path_for, doc_id)
    if path is not None and path.suffix.lower() in _INLINE_VIEW_EXTS:
        return RedirectResponse(url=f"/documents/{doc_id}/file", status_code=307)

    page = await run_in_threadpool(_render_view, doc_id, section)
    if page is None:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tài liệu với doc_id này."
        )
    return HTMLResponse(page)


@router.delete("/documents/{doc_id}", response_model=DocumentDeleteResponse)
async def delete_document(doc_id: str) -> DocumentDeleteResponse:
    """Remove all indexed chunks of one document (by ``doc_id``)."""
    n_chunks = await run_in_threadpool(indexer.count_document_points, doc_id)
    if n_chunks == 0:
        raise HTTPException(
            status_code=404, detail="Không tìm thấy tài liệu với doc_id này."
        )
    await run_in_threadpool(indexer.delete_document, doc_id)
    return DocumentDeleteResponse(doc_id=doc_id, deleted_chunks=n_chunks)
