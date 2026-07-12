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
from starlette.concurrency import run_in_threadpool

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


def _run_pipeline(path: Path, doc_type: DocType | None) -> IngestResponse:
    """Synchronous parse -> clean -> chunk -> enrich -> index for one file."""
    doc = route_to_parser(path, doc_type=doc_type)
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
) -> IngestResponse:
    """Ingest a single document (Markdown/DOCX/XLSX/glossary YAML)."""
    filename = _safe_filename(file.filename)
    uploads = settings.data_dir / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    dest = uploads / filename
    dest.write_bytes(await file.read())

    try:
        return await run_in_threadpool(_run_pipeline, dest, doc_type)
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc


@router.get("/documents", response_model=list[DocumentInfo])
async def list_documents() -> list[DocumentInfo]:
    """List documents currently indexed in Qdrant."""
    return await run_in_threadpool(indexer.list_documents)


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
