"""bge-reranker-v2-m3 cross-encoder reranking.

Reduces the RRF-fused hybrid-search hits down to ``settings.rerank_top_k`` for
generation (skill, section 5). Before scoring, the fused list is truncated to
``settings.rerank_candidates`` (already RRF-sorted) so the cross-encoder does
not pay for ranks that will never reach generation. The model is loaded lazily
and cached (mirrors ``ingestion/indexer.get_embedder``), so importing this
module is cheap and unit tests that inject a fake ``score_fn`` never pay for
the model load.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from app.config.settings import settings
from app.models.schemas import Hit

logger = logging.getLogger(__name__)

# Concurrent chat requests rerank in separate threadpool threads, but the fast
# (Rust) tokenizer inside FlagReranker is not thread-safe: parallel calls raise
# "RuntimeError: Already borrowed" or, worse, silently mis-tokenize and score
# every hit near 0 (observed dropping all hits below the rerank floor).
_score_lock = threading.Lock()

# (query, documents) -> relevance scores, aligned with documents, higher is better.
ScoreFn = Callable[[str, list[str]], list[float]]


@lru_cache
def get_reranker() -> Any:
    """Load and cache the bge-reranker-v2-m3 cross-encoder (CPU, offline weights)."""
    from FlagEmbedding import FlagReranker  # heavy import, kept lazy

    logger.info("Loading bge-reranker-v2-m3 from %s", settings.rerank_model_path)
    return FlagReranker(settings.rerank_model_path, use_fp16=False)


def _flag_rerank_scores(query: str, documents: list[str]) -> list[float]:
    if not documents:
        return []
    pairs = [[query, doc] for doc in documents]
    with _score_lock:
        scores = get_reranker().compute_score(
            pairs,
            normalize=True,
            max_length=settings.rerank_max_length,
        )
    # compute_score returns a bare float for a single pair instead of a list.
    return [scores] if isinstance(scores, float) else list(scores)


def _rerank_text(hit: Hit) -> str:
    """Chunk text as the cross-encoder sees it: doc/section prefix + display text.

    The prefix (same convention as ``embed_text`` in chunking.py) matters when
    the query names a document or product whose name never appears in the chunk
    body — e.g. benefit clauses of a brochure: without it the reranker prefers
    cover-page chunks that merely mention the product name over the actual
    benefit sections.
    """
    p = hit.payload
    return f"Tài liệu: {p.doc_title} > {p.section_path}\n\n{p.display_text}"


def _parent_key(hit: Hit) -> tuple[str, str | int]:
    """Identity of the parent window a hit would widen to in the prompt.

    A chunk with no parent is its own group, keyed by point id so it can never
    collide with another chunk (flat chunks, and points indexed before
    parent-child chunking existed).
    """
    payload = hit.payload
    if payload.parent_index is None:
        return ("", hit.point_id)
    return (payload.doc_id, payload.parent_index)


def _best_per_parent(ranked: list[Hit]) -> list[Hit]:
    """Keep only the best-scoring child of each parent window.

    Under parent-child chunking several children of one parent can survive
    reranking, and generation widens every hit to its parent — so keeping them
    all would spend the top_k budget re-sending one window instead of adding
    distinct material. ``ranked`` must already be sorted best-first.
    """
    seen: set[tuple[str, str | int]] = set()
    out: list[Hit] = []
    for hit in ranked:
        key = _parent_key(hit)
        if key not in seen:
            seen.add(key)
            out.append(hit)
    return out


def rerank(
    query: str,
    hits: list[Hit],
    *,
    top_k: int | None = None,
    candidates: int | None = None,
    min_score: float | None = None,
    min_ratio: float | None = None,
    score_fn: ScoreFn | None = None,
) -> list[Hit]:
    """Cross-encoder rerank of fused hits, cut to top_k.

    ``hits`` are assumed already sorted best-first (RRF order from hybrid
    search). Only the first ``candidates`` are scored — ranks beyond that
    almost never survive the top_k cut, and the cross-encoder is the
    latency bottleneck. Each scored hit uses its title/section-prefixed
    display text (see ``_rerank_text``). A hit is dropped when it scores
    below either floor: ``min_score`` (an absolute normalized 0-1 threshold)
    or ``min_ratio`` times the top hit's score (a relative floor that
    suppresses weak cross-document chunks padding the context when a strong,
    coherent top hit exists; ``min_ratio=0`` disables it). Dropping keeps
    generation from ever seeing context the reranker considers irrelevant; an
    empty result lets the chat endpoint refuse deterministically instead of
    trusting the LLM to. Surviving hits are collapsed to one child per parent
    window before the cut, so top_k means top_k distinct windows. Mutates and
    reuses each ``Hit``'s ``score`` in place (RRF score is no longer needed
    once reranked). Returns ``[]`` for empty input.
    """
    if not hits:
        return []
    top_k = top_k or settings.rerank_top_k
    if candidates is None:
        candidates = settings.rerank_candidates
    if candidates > 0:
        hits = hits[:candidates]
    if min_score is None:
        min_score = settings.rerank_min_score
    if min_ratio is None:
        min_ratio = settings.rerank_min_ratio
    score_fn = score_fn or _flag_rerank_scores

    scores = score_fn(query, [_rerank_text(hit) for hit in hits])
    for hit, score in zip(hits, scores):
        hit.score = float(score)

    # Effective floor = the stricter of the absolute and (top-relative) floors.
    top_score = max(hit.score for hit in hits)
    floor = max(min_score, top_score * min_ratio)
    kept = [hit for hit in hits if hit.score >= floor]
    if len(kept) < len(hits):
        logger.info(
            "rerank: dropped %d/%d hits below floor=%.3f "
            "(min_score=%.2f, min_ratio=%.2f, top=%.3f)",
            len(hits) - len(kept),
            len(hits),
            floor,
            min_score,
            min_ratio,
            top_score,
        )
    ranked = _best_per_parent(sorted(kept, key=lambda hit: hit.score, reverse=True))
    return ranked[:top_k]
