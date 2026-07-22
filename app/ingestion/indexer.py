"""Indexing: bge-m3 dense+sparse embeddings -> Qdrant.

bge-m3 (via FlagEmbedding, loaded from local weights for offline use) produces
BOTH a dense vector and sparse lexical weights from each chunk's ``embed_text``;
both are stored in one Qdrant collection under named vectors ``dense`` / ``sparse``
(skill, section 5). Ingestion is idempotent: a document's existing points (by
``doc_id``) are deleted before its chunks are upserted.

The heavy model is loaded lazily and cached, so importing this module is cheap
and unit tests that don't index never pay for it.
"""

from __future__ import annotations

import logging
import threading
import uuid
from functools import lru_cache
from typing import Any

from qdrant_client import QdrantClient, models

from app.config.settings import settings
from app.models.schemas import Chunk, DocumentInfo

logger = logging.getLogger(__name__)

# Deterministic point ids from (doc_id, chunk_index) so re-ingesting is stable.
_ID_NAMESPACE = uuid.UUID("6f4a1d9e-0b2c-4e77-9a1b-000000000001")

_DENSE = "dense"
_SPARSE = "sparse"

# The fast (Rust) tokenizer inside BGEM3FlagModel is not thread-safe; an ingest
# running in the threadpool while a chat request embeds its query would corrupt
# tokenization (same failure mode as the reranker — see retrieval/reranker.py).
_embed_lock = threading.Lock()


@lru_cache
def get_embedder() -> Any:
    """Load and cache the bge-m3 FlagEmbedding model (CPU, offline weights)."""
    from FlagEmbedding import BGEM3FlagModel  # heavy import, kept lazy

    logger.info("Loading bge-m3 embedder from %s", settings.embed_model_path)
    return BGEM3FlagModel(settings.embed_model_path, use_fp16=False)


@lru_cache
def get_client() -> QdrantClient:
    """Cached Qdrant client.

    With ``QDRANT_LOCAL_PATH`` set, qdrant-client runs EMBEDDED in this process
    and persists to that directory — the no-Docker deployment mode, no Qdrant
    server involved. The storage dir is single-process (file-locked), so e.g.
    eval/run_ragas.py must run while the API is stopped. Otherwise, classic
    server mode via ``QDRANT_URL``.
    """
    if settings.qdrant_local_path:
        logger.info("Using embedded Qdrant at %s", settings.qdrant_local_path)
        return QdrantClient(path=settings.qdrant_local_path)
    return QdrantClient(url=settings.qdrant_url)


def count_tokens(text: str) -> int:
    """Token count via the bge-m3 tokenizer (for chunking); falls back safely."""
    try:
        tok = get_embedder().tokenizer
        with _embed_lock:
            return len(tok(text, add_special_tokens=True)["input_ids"])
    except Exception:  # pragma: no cover - offline/model-less fallback
        from app.ingestion.chunking import default_token_counter

        return default_token_counter(text)


def _to_sparse(lexical_weights: dict[str, float]) -> models.SparseVector:
    """Convert bge-m3 lexical weights (token_id -> weight) to a Qdrant sparse vec."""
    indices = [int(k) for k in lexical_weights]
    values = [float(v) for v in lexical_weights.values()]
    return models.SparseVector(indices=indices, values=values)


def embed_texts(
    texts: list[str],
) -> tuple[list[list[float]], list[models.SparseVector]]:
    """Embed texts, returning aligned dense vectors and sparse vectors."""
    with _embed_lock:
        out = get_embedder().encode(
            texts,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )
    dense = [vec.tolist() for vec in out["dense_vecs"]]
    sparse = [_to_sparse(w) for w in out["lexical_weights"]]
    return dense, sparse


def ensure_collection() -> None:
    """Create the Qdrant collection with dense+sparse named vectors if missing."""
    client = get_client()
    if client.collection_exists(settings.qdrant_collection):
        return
    distance = models.Distance[settings.dense_distance.upper()]
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config={
            _DENSE: models.VectorParams(
                size=settings.dense_vector_size, distance=distance
            )
        },
        sparse_vectors_config={_SPARSE: models.SparseVectorParams()},
    )
    logger.info("Created Qdrant collection '%s'", settings.qdrant_collection)


def count_document_points(doc_id: str) -> int:
    """Number of indexed points for a document (0 when unknown / no collection)."""
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return 0
    result = client.count(
        collection_name=settings.qdrant_collection,
        count_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id", match=models.MatchValue(value=doc_id)
                )
            ]
        ),
        exact=True,
    )
    return result.count


def get_document_source_filename(doc_id: str) -> str | None:
    """Basename of the originally uploaded file for ``doc_id``, or None.

    None when the document has no points, or was ingested before
    ``source_filename`` was tracked, or has no backing upload (e.g. glossary
    entries built in-memory).
    """
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return None
    records, _ = client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id", match=models.MatchValue(value=doc_id)
                )
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not records:
        return None
    return (records[0].payload or {}).get("source_filename")


def get_document_meta(doc_id: str) -> dict[str, Any] | None:
    """Current title / type / department / source filename for ``doc_id``, or None.

    Read from the document's first stored point (these fields are identical
    across all of a document's chunks). Used by the metadata-edit endpoint to
    fill in fields the caller didn't change. None when the document has no points.
    """
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return None
    records, _ = client.scroll(
        collection_name=settings.qdrant_collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id", match=models.MatchValue(value=doc_id)
                )
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )
    if not records:
        return None
    p = records[0].payload or {}
    return {
        "doc_title": p.get("doc_title", ""),
        "doc_type": p.get("doc_type", "other"),
        "department": p.get("department"),
        "source_filename": p.get("source_filename"),
    }


def set_document_metadata(
    doc_id: str,
    *,
    doc_title: str | None = None,
    doc_type: str | None = None,
    department: str | None = None,
    set_department: bool = False,
) -> None:
    """Update selected payload fields across all of a document's points.

    Metadata-only: does NOT re-embed. Use for ``doc_type``/``department`` edits
    (neither is part of ``embed_text``) and for renaming documents that have no
    source file to re-ingest from. ``department`` is only written when
    ``set_department`` is True (so ``None`` can explicitly clear it, distinct
    from "leave unchanged"). No-op when nothing is selected.
    """
    payload: dict[str, Any] = {}
    if doc_title is not None:
        payload["doc_title"] = doc_title
    if doc_type is not None:
        payload["doc_type"] = doc_type
    if set_department:
        payload["department"] = department
    if not payload:
        return
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return
    client.set_payload(
        collection_name=settings.qdrant_collection,
        payload=payload,
        points=models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id", match=models.MatchValue(value=doc_id)
                )
            ]
        ),
    )


def get_document_chunks(doc_id: str) -> list[dict[str, Any]]:
    """All stored chunks of a document, ordered by ``chunk_index``.

    Returns the payload fields the viewer needs to rebuild a readable rendering
    of the source (``display_text`` is the clean Markdown+LaTeX). Empty list
    when the document has no points. Used by the document-viewer endpoint, which
    reconstructs the source from chunks so citations stay clickable even for
    documents that have no backing upload file (e.g. batch-ingested corpora).
    """
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return []
    out: list[dict[str, Any]] = []
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id", match=models.MatchValue(value=doc_id)
                    )
                ]
            ),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        out.extend(rec.payload or {} for rec in records)
        if offset is None:
            break
    out.sort(key=lambda p: p.get("chunk_index", 0))
    return out


def delete_document(doc_id: str) -> None:
    """Remove all points for a document (idempotent re-ingest / deletion)."""
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id", match=models.MatchValue(value=doc_id)
                    )
                ]
            )
        ),
    )


def index_chunks(chunks: list[Chunk]) -> int:
    """Embed and upsert chunks; deletes each doc's prior points first.

    Returns the number of points written. Assumes all chunks belong to one
    ``doc_id`` (the ingest flow calls it per document).
    """
    if not chunks:
        return 0
    ensure_collection()
    doc_ids = {c.doc_id for c in chunks}
    for doc_id in doc_ids:
        delete_document(doc_id)

    dense, sparse = embed_texts([c.embed_text for c in chunks])
    points: list[models.PointStruct] = []
    for chunk, dvec, svec in zip(chunks, dense, sparse):
        pid = str(uuid.uuid5(_ID_NAMESPACE, f"{chunk.doc_id}:{chunk.chunk_index}"))
        points.append(
            models.PointStruct(
                id=pid,
                vector={_DENSE: dvec, _SPARSE: svec},
                payload=chunk.to_payload().model_dump(),
            )
        )
    get_client().upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info("Upserted %d points for doc_id(s) %s", len(points), doc_ids)
    return len(points)


def list_documents() -> list[DocumentInfo]:
    """Aggregate indexed points into per-document summaries."""
    client = get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return []
    agg: dict[str, dict[str, Any]] = {}
    offset = None
    while True:
        records, offset = client.scroll(
            collection_name=settings.qdrant_collection,
            with_payload=True,
            with_vectors=False,
            limit=256,
            offset=offset,
        )
        for rec in records:
            p = rec.payload or {}
            doc_id = p.get("doc_id")
            if not doc_id:
                continue
            entry = agg.setdefault(
                doc_id,
                {
                    "doc_id": doc_id,
                    "doc_title": p.get("doc_title", ""),
                    "doc_type": p.get("doc_type", "other"),
                    "department": p.get("department"),
                    "n_chunks": 0,
                    "ingested_at": p.get("ingested_at"),
                },
            )
            entry["n_chunks"] += 1
        if offset is None:
            break
    return [DocumentInfo(**e) for e in agg.values()]
