"""``GET /metrics/summary`` — aggregated view over ``query_timings.jsonl``.

Day 4 / 2026-08-05 audit (ADM1's follow-on): reads the same metadata-only
JSONL ``app/query_timing.py`` already writes — never query/answer text, ever
— and aggregates it into the numbers a non-technical manager actually wants:
refusal rate, latency percentiles, answer-mode breakdown, retrieved-hit
count. Feeds the "Chất lượng & hiệu năng" section of ``app/static/index.html``
so nobody has to read a raw JSONL file by hand. Read-only, local-only, no
external calls.
"""

from __future__ import annotations

import json
import logging
import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app import auth
from app.config.settings import settings
from app.models.schemas import DocumentInfo

logger = logging.getLogger("bv-ai-agent.metrics")

router = APIRouter(tags=["metrics"])

_MODES = ("grounded", "advisory", "hybrid", "refusal")

# Fallback bin width for _nice_bin_width when there's no data to size against;
# _latency_histogram otherwise derives the real width from the observed max.
_LATENCY_BIN_MS = 500.0
_LATENCY_N_BINS = 12


class ModeBreakdown(BaseModel):
    grounded: int = 0
    advisory: int = 0
    hybrid: int = 0
    refusal: int = 0
    other: int = 0  # e.g. "meta"/"clarification", or any future mode label


class HeatmapCell(BaseModel):
    """Question count for one (weekday, hour) cell, Mon=0 .. Sun=6, hour in [0,23]."""

    weekday: int
    hour: int
    count: int


class TopDocument(BaseModel):
    doc_id: str
    doc_title: str
    count: int  # number of times this document was among the retrieved hits


class LatencyBin(BaseModel):
    start_ms: float
    end_ms: float | None  # None only when there is no data to size bins from
    count: int


class DepartmentCount(BaseModel):
    department: str  # "Không đặt" for documents with no department set
    count: int


class DailyCount(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    count: int


class MetricsSummary(BaseModel):
    """One aggregated snapshot over the selected time window."""

    window_hours: float | None  # None/0 = all time
    n_requests: int
    refusal_rate: float | None
    mode_breakdown: ModeBreakdown
    elapsed_ms_p50: float | None
    elapsed_ms_p95: float | None
    n_hits_mean: float | None
    n_hits_p50: float | None
    n_hits_max: int | None
    daily_volume: list[DailyCount]
    heatmap: list[HeatmapCell]
    top_documents: list[TopDocument]
    latency_histogram: list[LatencyBin]
    # Document-store snapshots (not time-windowed — there is no per-query
    # department field to aggregate, see REDESIGN_PROMPT.md §Metrics).
    n_documents: int
    documents_by_department: list[DepartmentCount]
    recent_documents: list[DocumentInfo]


def _percentile(values: list[float], p: float) -> float | None:
    """Nearest-rank percentile (``p`` in [0, 100]); ``None`` for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round(p / 100 * (len(ordered) - 1))))
    return ordered[idx]


def _read_records(since: datetime | None) -> list[dict]:
    """Parse ``query_timings.jsonl``, optionally only entries at/after ``since``.

    Tolerant of a partially-written last line (the process could be mid-append)
    and of records from before a schema field existed — both are skipped or
    treated as missing rather than raising.
    """
    path = settings.query_timing_log_path
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if since is not None:
                try:
                    ts = datetime.fromisoformat(record.get("ts", ""))
                except ValueError:
                    continue
                if ts < since:
                    continue
            records.append(record)
    return records


def _record_timestamp(record: dict) -> datetime | None:
    try:
        return datetime.fromisoformat(record.get("ts", ""))
    except ValueError:
        return None


def _daily_volume(records: list[dict]) -> list[DailyCount]:
    counts: Counter[str] = Counter()
    for record in records:
        ts = _record_timestamp(record)
        if ts is not None:
            counts[ts.date().isoformat()] += 1
    return [DailyCount(date=d, count=c) for d, c in sorted(counts.items())]


def _heatmap(records: list[dict]) -> list[HeatmapCell]:
    counts: Counter[tuple[int, int]] = Counter()
    for record in records:
        ts = _record_timestamp(record)
        if ts is not None:
            counts[(ts.weekday(), ts.hour)] += 1
    return [
        HeatmapCell(weekday=weekday, hour=hour, count=counts.get((weekday, hour), 0))
        for weekday in range(7)
        for hour in range(24)
    ]


def _top_documents(records: list[dict], *, limit: int = 6) -> list[TopDocument]:
    counts: Counter[str] = Counter()
    for record in records:
        for hit in record.get("hits") or []:
            doc_id = hit.get("doc_id")
            if doc_id:
                counts[doc_id] += 1
    if not counts:
        return []
    # Lazy import: pulls in the Qdrant client, kept off the module's import path
    # so tests exercising pure aggregation (summarize()) never need it.
    from app.ingestion import indexer

    try:
        titles = {doc.doc_id: doc.doc_title for doc in indexer.list_documents()}
    except Exception:  # noqa: BLE001 - Qdrant down must degrade, not 500 the whole panel
        logger.warning(
            "Could not fetch document titles for top_documents", exc_info=True
        )
        titles = {}
    return [
        TopDocument(doc_id=doc_id, doc_title=titles.get(doc_id, doc_id), count=count)
        for doc_id, count in counts.most_common(limit)
    ]


def _nice_bin_width(rough: float) -> float:
    """Round ``rough`` up to a 1/2/5 * 10^k step, so bin edges read like "2.5s" not "2,847ms"."""
    if rough <= 0:
        return _LATENCY_BIN_MS
    magnitude = 10 ** math.floor(math.log10(rough))
    for mult in (1, 2, 5, 10):
        step = mult * magnitude
        if step >= rough:
            return step
    return 10 * magnitude


def _latency_histogram(records: list[dict]) -> list[LatencyBin]:
    """Fixed-width bins sized to the ACTUAL latency range, not a hardcoded guess.

    A 500ms-wide bin (fine for a sub-3s SaaS chatbot) is useless here: this app
    runs a local 7-8B model end-to-end (retrieval + rerank + generation), so
    real answers land in the tens of seconds — a fixed 500ms bin would dump
    every single request into one "6s+" overflow bucket. Sizing the bin width
    off the observed max keeps the histogram informative regardless of how
    fast or slow the underlying model/hardware is.
    """
    values = [
        r["elapsed_ms"]
        for r in records
        if isinstance(r.get("elapsed_ms"), (int, float))
    ]
    if not values:
        return []
    bin_ms = _nice_bin_width(max(values) / _LATENCY_N_BINS)
    bins = [0] * _LATENCY_N_BINS
    for value in values:
        idx = min(_LATENCY_N_BINS - 1, int(value // bin_ms))
        bins[idx] += 1
    return [
        LatencyBin(start_ms=i * bin_ms, end_ms=(i + 1) * bin_ms, count=bins[i])
        for i in range(_LATENCY_N_BINS)
    ]


def _document_store_snapshot() -> tuple[int, list[DepartmentCount], list[DocumentInfo]]:
    """Documents-by-department + most-recently-ingested — from the doc store, not the query log.

    Per-query department isn't recorded anywhere (no such field on ``Chunk`` /
    ``QdrantPayload``), so the department breakdown the kit shows as a
    who's-asking donut is reframed here as documents-by-department instead —
    real data, different question answered.

    Unlike the rest of ``MetricsSummary`` (pure ``query_timings.jsonl``
    aggregation), this reaches into Qdrant. A Qdrant outage must degrade this
    one panel's fields to empty/zero rather than 500 the whole endpoint — the
    timing-log stats are still worth showing when Qdrant is briefly down.
    """
    from app.ingestion import indexer

    try:
        docs = indexer.list_documents()
    except Exception:  # noqa: BLE001 - see docstring
        logger.warning(
            "Could not read document store for metrics snapshot", exc_info=True
        )
        return 0, [], []
    dept_counts: Counter[str] = Counter(doc.department or "Không đặt" for doc in docs)
    by_department = [
        DepartmentCount(department=dept, count=count)
        for dept, count in dept_counts.most_common()
    ]
    recent = sorted(
        (doc for doc in docs if doc.ingested_at),
        key=lambda doc: doc.ingested_at,
        reverse=True,
    )[:5]
    return len(docs), by_department, recent


def summarize(records: list[dict], *, window_hours: float | None) -> MetricsSummary:
    """Pure aggregation over already-loaded records — unit-testable without I/O.

    Document-store fields (``n_documents``, ``documents_by_department``,
    ``recent_documents``) are NOT derived from ``records`` and are filled in
    separately by the endpoint, since they come from Qdrant rather than the
    timing log; they default to empty/zero here so this function stays usable
    without a live index (e.g. in unit tests).
    """
    n = len(records)
    breakdown = ModeBreakdown()
    for record in records:
        mode = record.get("mode")
        if mode in _MODES:
            setattr(breakdown, mode, getattr(breakdown, mode) + 1)
        else:
            breakdown.other += 1

    elapsed = [
        r["elapsed_ms"]
        for r in records
        if isinstance(r.get("elapsed_ms"), (int, float))
    ]
    hits = [r["n_hits"] for r in records if isinstance(r.get("n_hits"), (int, float))]

    return MetricsSummary(
        window_hours=window_hours,
        n_requests=n,
        refusal_rate=(breakdown.refusal / n) if n else None,
        mode_breakdown=breakdown,
        elapsed_ms_p50=_percentile(elapsed, 50),
        elapsed_ms_p95=_percentile(elapsed, 95),
        n_hits_mean=(sum(hits) / len(hits)) if hits else None,
        n_hits_p50=_percentile(hits, 50),
        n_hits_max=int(max(hits)) if hits else None,
        daily_volume=_daily_volume(records),
        heatmap=_heatmap(records),
        top_documents=_top_documents(records),
        latency_histogram=_latency_histogram(records),
        n_documents=0,
        documents_by_department=[],
        recent_documents=[],
    )


@router.get(
    "/metrics/summary",
    response_model=MetricsSummary,
    dependencies=[Depends(auth.require_admin)],
)
async def metrics_summary(
    hours: float = Query(
        default=24.0,
        ge=0,
        description="Time window in hours; 0 means all time.",
    ),
) -> MetricsSummary:
    since = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
    records = _read_records(since)
    summary = summarize(records, window_hours=hours or None)
    n_documents, by_department, recent = _document_store_snapshot()
    summary.n_documents = n_documents
    summary.documents_by_department = by_department
    summary.recent_documents = recent
    return summary
