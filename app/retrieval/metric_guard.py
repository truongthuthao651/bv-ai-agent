"""Drop fee/interest chunks from benefit-payout queries.

A "claim bao nhiêu%?" question plus any ``%``-by-năm-hợp-đồng table is enough
for a small local model to relabel lãi suất cam kết as tỷ lệ bồi thường.
Product-scope still passes (same product). This guard removes chunks whose
section/body are clearly fee or guaranteed-interest material when the query is
asking about a benefit payout — so generation never sees the wrong schedule.

Pure and offline — unit-tested without Qdrant or an LLM.
"""

from __future__ import annotations

import re

from app.models.schemas import Hit
from app.text_utils import fold_text as _fold

# Benefit-payout intent: event + asking for amount/%/claim (diacritic-folded).
_PAYOUT_MARKERS: tuple[str, ...] = (
    "claim",
    "boi thuong",
    "chi tra",
    "bao nhieu",
    "duoc bao nhieu",
    "phan tram",
)
_EVENT_MARKERS: tuple[str, ...] = (
    "tu vong",
    "chet",
    "thuong tat",
    "tai nan",
    "dao han",
    "quyen loi",
)

# Chunk is fee / guaranteed-interest (not a death-benefit schedule).
_FEE_INTEREST_MARKERS: tuple[str, ...] = (
    "lai suat cam ket",
    "lai suat toi thieu",
    "lai suat dam bao",
    "lai suat quy",
    "phi ban dau",
    "phi quan ly quy",
    "phi quan ly hop dong",
    "phi rut tien",
    "phi dinh ky",
)


def is_benefit_payout_query(query: str) -> bool:
    """True when the user is asking how much / what % a benefit pays out."""
    if not query.strip():
        return False
    folded = _fold(query)
    has_payout = any(m in folded for m in _PAYOUT_MARKERS) or bool(
        re.search(r"\d+\s*%|%\s*", query)
    )
    has_event = any(m in folded for m in _EVENT_MARKERS)
    # "claim bao nhiêu%" without naming the event still counts — the %+claim
    # pair is the failure mode observed in production.
    if "claim" in folded and (
        "%" in query or "phan tram" in folded or "bao nhieu" in folded
    ):
        return True
    return has_payout and has_event


def looks_like_fee_or_interest(hit: Hit) -> bool:
    """True when the hit is a fee / guaranteed-interest section or table.

    Matches against ``context_text`` — the parent window under parent-child
    chunking — because that is what generation would receive: a child that is a
    harmless-looking paragraph can still be cut from a lãi suất cam kết table
    whose caption only appears in the parent.
    """
    blob = _fold(f"{hit.payload.section_path}\n{hit.payload.context_text}")
    return any(m in blob for m in _FEE_INTEREST_MARKERS)


def filter_metric_mismatch(query: str, hits: list[Hit]) -> list[Hit]:
    """Remove fee/interest hits from benefit-payout queries.

    If every hit would be removed, returns ``[]`` so the chat endpoint refuses
    rather than answering a claim-% question from an interest-rate table.
    Non-payout queries are returned unchanged.
    """
    if not hits or not is_benefit_payout_query(query):
        return hits
    kept = [h for h in hits if not looks_like_fee_or_interest(h)]
    return kept
