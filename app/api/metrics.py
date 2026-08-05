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
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.config.settings import settings

router = APIRouter(tags=["metrics"])

_MODES = ("grounded", "advisory", "hybrid", "refusal")


class ModeBreakdown(BaseModel):
    grounded: int = 0
    advisory: int = 0
    hybrid: int = 0
    refusal: int = 0
    other: int = 0  # e.g. "meta"/"clarification", or any future mode label


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


def summarize(records: list[dict], *, window_hours: float | None) -> MetricsSummary:
    """Pure aggregation over already-loaded records — unit-testable without I/O."""
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
    )


@router.get("/metrics/summary", response_model=MetricsSummary)
async def metrics_summary(
    hours: float = Query(
        default=24.0,
        ge=0,
        description="Time window in hours; 0 means all time.",
    ),
) -> MetricsSummary:
    since = datetime.now(timezone.utc) - timedelta(hours=hours) if hours else None
    records = _read_records(since)
    return summarize(records, window_hours=hours or None)
