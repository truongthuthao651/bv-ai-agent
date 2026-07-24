"""Per-product retrieval for multi-product (comparison) questions.

A single global ``rerank_top_k`` pool starves comparison answers: one product's
overview chunks crowd out the other product's benefit sections, so the model
honestly says "không nêu rõ" for facts that *are* in the corpus but never made
it into context.

When the query names ≥2 products, run hybrid search + rerank **per product** —
each scoped to that product's own doc_ids *before* any top-k cut — keep a quota
of chunks each, then merge. Pure merge / label helpers are unit-tested without
Qdrant; the chat endpoint wires the live search/rerank callables.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from app.config.settings import settings
from app.models.schemas import Hit
from app.retrieval.product_scope import named_product_labels, title_covers_product

logger = logging.getLogger(__name__)

# (query, doc_ids or None) -> hits. Passing doc_ids scopes the hybrid search to
# one product's documents so it gets a full candidate pool of its own.
SearchFn = Callable[[str, list[str] | None], list[Hit]]
RerankFn = Callable[[str, list[Hit], int], list[Hit]]


def is_multi_product_query(query: str, *, titles: list[str] | None = None) -> bool:
    """True when ``query`` explicitly names at least two distinct products."""
    return len(named_product_labels(query, titles=titles)) >= 2


def focused_query(standalone: str, product_label: str) -> str:
    """Bias retrieval toward one product without dropping comparison criteria."""
    return f"{standalone.rstrip()} (tài liệu: {product_label})"


def merge_per_product_hits(
    per_product: list[list[Hit]],
    *,
    total_cap: int,
) -> list[Hit]:
    """Round-robin merge of per-product hit lists, deduped by ``point_id``.

    Round-robin keeps each product represented early in the context instead of
    letting a high-scoring product fill the entire budget first.
    """
    if total_cap <= 0 or not per_product:
        return []
    seen: set[str] = set()
    merged: list[Hit] = []
    idx = 0
    while len(merged) < total_cap:
        added = False
        for hits in per_product:
            if idx >= len(hits):
                continue
            hit = hits[idx]
            if hit.point_id in seen:
                continue
            seen.add(hit.point_id)
            merged.append(hit)
            added = True
            if len(merged) >= total_cap:
                break
        if not added:
            break
        idx += 1
    return merged


def product_doc_ids(product_label: str, docs: list[tuple[str, str]]) -> list[str]:
    """doc_ids of indexed documents whose title covers ``product_label``.

    ``docs`` is a list of ``(doc_id, doc_title)``. Empty means the product has no
    title match (abbreviated filenames) — callers then search unfiltered and fall
    back to title post-filtering.
    """
    return [
        doc_id for doc_id, title in docs if title_covers_product(title, product_label)
    ]


def _load_indexed_docs() -> list[tuple[str, str]]:
    """Best-effort ``(doc_id, doc_title)`` pairs; empty when Qdrant is unavailable."""
    try:
        from app.ingestion import indexer

        return [(d.doc_id, d.doc_title) for d in indexer.list_documents()]
    except Exception:  # pragma: no cover - Qdrant locked/offline
        return []


def prefer_matching_titles(hits: list[Hit], product_label: str) -> list[Hit]:
    """Keep hits whose doc title covers ``product_label``; else leave unchanged.

    Cross-product benefit clauses can still clear the rerank floor; preferring
    title matches stops the wrong product's chunks from filling this product's
    quota. Falls back to the full list when nothing matches (abbreviated titles).
    """
    matched = [
        h for h in hits if title_covers_product(h.payload.doc_title, product_label)
    ]
    return matched if matched else hits


def retrieve_multi_product(
    standalone_query: str,
    *,
    search_fn: SearchFn,
    rerank_fn: RerankFn,
    expand_fn: Callable[[str], str] | None = None,
    per_product_top_k: int | None = None,
    max_products: int | None = None,
    titles: list[str] | None = None,
    docs: list[tuple[str, str]] | None = None,
    labels: list[str] | None = None,
) -> list[Hit]:
    """Search + rerank once per named product, then merge with equal quota.

    Each product is scoped to its own documents *before* any top-k cut: the
    hybrid search is filtered by that product's doc_ids, and the rerank pool is
    title-filtered before being cut to ``per_k``. Cutting first (search -> rerank
    top-k -> filter) let the better-parsed product's chunks fill the global cut,
    leaving the other product only its cover-page chunks — the model then said
    "không nêu rõ" for facts that were indexed all along. Scoping first also
    neutralizes the doc-title prefix in ``reranker._rerank_text``: with all
    candidates from one product, that prefix is constant and stops biasing the
    ranking toward headings that merely repeat the product name.

    ``search_fn`` / ``rerank_fn`` are injectable for tests. ``expand_fn`` defaults
    to identity (caller may pass glossary expansion). ``titles`` are indexed
    document titles used to resolve informal product nicknames; ``docs`` are
    ``(doc_id, doc_title)`` pairs used to scope the search (loaded from Qdrant
    when omitted). ``labels`` overrides product detection from the query text —
    used for advisory follow-ups ("KH sẽ chọn sản phẩm nào?") that name no
    product themselves but continue a comparison of documents cited earlier.
    """
    labels = labels or named_product_labels(standalone_query, titles=titles)
    if len(labels) < 2:
        return []

    per_k = per_product_top_k or settings.comparison_per_product_top_k
    cap_n = max_products or settings.comparison_max_products
    labels = labels[:cap_n]
    expand = expand_fn or (lambda q: q)
    known_docs = _load_indexed_docs() if docs is None else docs

    buckets: list[list[Hit]] = []
    for label in labels:
        focused = focused_query(standalone_query, label)
        doc_ids = product_doc_ids(label, known_docs)
        raw = search_fn(expand(focused), doc_ids or None)
        # Belt-and-braces: the doc filter already scopes the pool when doc_ids
        # resolved; this also handles the unfiltered fallback (no title match).
        same_product = prefer_matching_titles(raw, label)
        ranked = rerank_fn(focused, same_product, per_k)
        buckets.append(ranked[:per_k])
        logger.info(
            "comparison retrieval: product=%r doc_ids=%d pool=%d scoped=%d kept=%d",
            label,
            len(doc_ids),
            len(raw),
            len(same_product),
            len(buckets[-1]),
        )

    merged = merge_per_product_hits(buckets, total_cap=per_k * len(labels))
    logger.info(
        "comparison retrieval: products=%s per_k=%d merged=%d",
        labels,
        per_k,
        len(merged),
    )
    return merged
