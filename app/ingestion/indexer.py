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


@lru_cache
def get_embedder() -> Any:
    """Load and cache the bge-m3 FlagEmbedding model (CPU, offline weights)."""
    from FlagEmbedding import BGEM3FlagModel  # heavy import, kept lazy

    logger.info("Loading bge-m3 embedder from %s", settings.embed_model_path)
    return BGEM3FlagModel(settings.embed_model_path, use_fp16=False)


@lru_cache
def get_client() -> QdrantClient:
    """Cached Qdrant client."""
    return QdrantClient(url=settings.qdrant_url)


def count_tokens(text: str) -> int:
    """Token count via the bge-m3 tokenizer (for chunking); falls back safely."""
    try:
        tok = get_embedder().tokenizer
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
