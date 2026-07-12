"""bge-reranker-v2-m3 cross-encoder reranking.

Reduces the RRF-fused hybrid-search hits down to ``settings.rerank_top_k`` for
generation (skill, section 5). The model is loaded lazily and cached (mirrors
``ingestion/indexer.get_embedder``), so importing this module is cheap and
unit tests that inject a fake ``score_fn`` never pay for the model load.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from app.config.settings import settings
from app.models.schemas import Hit

logger = logging.getLogger(__name__)

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
    scores = get_reranker().compute_score(pairs, normalize=True)
    # compute_score returns a bare float for a single pair instead of a list.
    return [scores] if isinstance(scores, float) else list(scores)


def rerank(
    query: str,
    hits: list[Hit],
    *,
    top_k: int | None = None,
    min_score: float | None = None,
    score_fn: ScoreFn | None = None,
) -> list[Hit]:
    """Cross-encoder rerank of fused hits against ``display_text``, cut to top_k.

    Hits scoring below ``min_score`` (normalized 0-1) are dropped so generation
    never sees context the reranker considers irrelevant; an empty result lets
    the chat endpoint refuse deterministically instead of trusting the LLM to.
    Mutates and reuses each ``Hit``'s ``score`` in place (RRF score is no longer
    needed once reranked). Returns ``[]`` for empty input.
    """
    if not hits:
        return []
    top_k = top_k or settings.rerank_top_k
    if min_score is None:
        min_score = settings.rerank_min_score
    score_fn = score_fn or _flag_rerank_scores

    scores = score_fn(query, [hit.payload.display_text for hit in hits])
    for hit, score in zip(hits, scores):
        hit.score = float(score)

    kept = [hit for hit in hits if hit.score >= min_score]
    if len(kept) < len(hits):
        logger.info(
            "rerank: dropped %d/%d hits below min_score=%.2f",
            len(hits) - len(kept),
            len(hits),
            min_score,
        )
    ranked = sorted(kept, key=lambda hit: hit.score, reverse=True)
    return ranked[:top_k]
