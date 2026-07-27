"""Hybrid retriever: dense + sparse search, fused with Reciprocal Rank Fusion.

Qdrant's built-in query fusion doesn't expose a configurable RRF constant, so
fusion is computed here in plain Python instead — that also keeps the fusion
math unit-testable without a live Qdrant (skill, section 5). Top-k and the RRF
constant are settings (``retrieve_top_k``, ``rrf_k``), never hardcoded.
"""

from __future__ import annotations

import logging

from qdrant_client import models

from app.config.settings import settings
from app.ingestion import indexer
from app.models.schemas import Hit, QdrantPayload

logger = logging.getLogger(__name__)

_DENSE = "dense"
_SPARSE = "sparse"


def rrf_fuse(rankings: list[list[str]], k: int) -> dict[str, float]:
    """Reciprocal Rank Fusion over one or more ranked id lists.

    Each ranking is a list of ids in descending relevance order (rank 1 = most
    relevant). An id absent from a ranking simply contributes 0 from it. Returns
    id -> fused score (higher is better); does not sort or truncate.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return scores


def _build_filter(filters: dict[str, str | list[str]] | None) -> models.Filter | None:
    """Build an AND-filter from a flat dict, if any given.

    A string value matches that field exactly; a list value matches any of its
    entries (``MatchAny``) — used to scope a search to one product's documents,
    which may be several doc_ids under one product name.
    """
    if not filters:
        return None
    conditions: list[models.FieldCondition] = []
    for key, value in filters.items():
        match: models.Match
        if isinstance(value, (list, tuple, set)):
            match = models.MatchAny(any=list(value))
        else:
            match = models.MatchValue(value=value)
        conditions.append(models.FieldCondition(key=key, match=match))
    return models.Filter(must=conditions)


def hybrid_search(
    query: str,
    *,
    filters: dict[str, str | list[str]] | None = None,
    top_k: int | None = None,
    rrf_k: int | None = None,
) -> list[Hit]:
    """Dense+sparse hybrid search over the Qdrant collection, fused via RRF.

    ``filters`` is a flat field->value map (e.g. ``{"doc_type": "policy"}``); a
    list value matches any of its entries (``{"doc_id": [id1, id2]}``).
    Returns an empty list (rather than raising) when the collection doesn't exist
    yet, e.g. before the first document has been ingested.
    """
    top_k = top_k or settings.retrieve_top_k
    rrf_k = rrf_k or settings.rrf_k

    client = indexer.get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return []

    query_filter = _build_filter(filters)
    dense_vecs, sparse_vecs = indexer.embed_texts([query])

    dense_response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=dense_vecs[0],
        using=_DENSE,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )
    sparse_response = client.query_points(
        collection_name=settings.qdrant_collection,
        query=sparse_vecs[0],
        using=_SPARSE,
        limit=top_k,
        query_filter=query_filter,
        with_payload=True,
    )

    payloads: dict[str, dict] = {}
    rankings: list[list[str]] = []
    for response in (dense_response, sparse_response):
        ranking: list[str] = []
        for point in response.points:
            pid = str(point.id)
            ranking.append(pid)
            payloads.setdefault(pid, point.payload or {})
        rankings.append(ranking)

    fused = rrf_fuse(rankings, rrf_k)
    ranked_ids = sorted(fused, key=lambda pid: fused[pid], reverse=True)
    return [
        Hit(point_id=pid, score=fused[pid], payload=QdrantPayload(**payloads[pid]))
        for pid in ranked_ids
    ]
