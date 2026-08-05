"""Local, metadata-only query timing: a user-facing latency footer + a JSONL log.

Two related things live here:

* ``response_time_footer`` — the small "⏱ Thời gian trả lời: 1m55s" line appended
  below an answer so the employee sees how long their question took, measured
  end-to-end (from request arrival to the answer being complete, including the
  slow retrieval/rerank phase, not just token generation).
* ``log_query_timing`` — one append-only JSONL record per answered question so
  latency can be analysed and fed back into evaluation over time.

Strictly LOCAL and privacy-preserving: it writes one line to a file on this
machine and makes NO network call — consistent with the air-gapped design, so
it is not telemetry in the phone-home sense CLAUDE.md forbids. It deliberately
records NO query or answer text (confidentiality — see the security rules),
only coarse metadata: timings, a mode label, the hit count, and text lengths.

The timer uses ``time.perf_counter()``; the endpoint captures the start value at
request arrival and threads a ``TimingContext`` down into generation, which is
where a streamed answer actually finishes.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config.settings import settings
from app.models.schemas import Hit

logger = logging.getLogger("bv-ai-agent.query_timing")


def format_elapsed(seconds: float) -> str:
    """Compact human duration: ``"45s"`` under a minute, else ``"1m55s"``."""
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    return f"{minutes}m{secs:02d}s" if minutes else f"{secs}s"


@dataclass
class TimingContext:
    """Per-request timing state, threaded from the endpoint into generation.

    ``mode`` is a coarse label for the answer path taken (``grounded`` /
    ``advisory`` / ``hybrid`` / ``refusal``), used only for aggregate analysis.
    """

    started_at: float  # time.perf_counter() captured at request arrival
    mode: str
    n_hits: int = 0
    query_chars: int = 0
    stream: bool = True
    # ADM1 (2026-08-05 audit): enough to reconstruct what a bad answer saw,
    # without ever logging the query/answer text itself. ``hits`` holds only
    # doc_id/section_path/score (never chunk text) per Hit, taken as-is from
    # ResponsePlan.hits — see log_query_timing for the compact record shape.
    hits: list[Hit] = field(default_factory=list)
    advisory: bool = False
    coverage: bool = False
    scope_labels: list[str] = field(default_factory=list)
    # Set by generator.py mid-generation (this object is threaded by
    # reference into generation) when a coverage turn goes through
    # coverage_gate.py's correction path: "none" (verdict was fine as
    # generated), "regenerated" (a corrected retry was accepted), or
    # "fallback" (the retry also failed and the deterministic enumeration
    # was used instead). None for non-coverage turns.
    coverage_gate_outcome: str | None = None

    def elapsed_s(self) -> float:
        """Seconds since the request arrived (never negative)."""
        return max(0.0, time.perf_counter() - self.started_at)


def response_time_footer(ctx: TimingContext | None) -> str:
    """The "⏱ Thời gian trả lời: …" line to append below an answer, or ``""``.

    Returns empty when timing wasn't requested for this path (e.g. Open WebUI
    meta-tasks) or when ``settings.show_response_time`` is off.
    """
    if ctx is None or not settings.show_response_time:
        return ""
    return f"\n\n_⏱ Thời gian trả lời: {format_elapsed(ctx.elapsed_s())}_"


def log_query_timing(
    ctx: TimingContext | None,
    *,
    answer_chars: int,
    first_token_s: float | None = None,
) -> None:
    """Append one metadata-only JSONL timing record. Best-effort, never raises.

    No-op when timing wasn't requested or ``query_timing_log_enabled`` is off.
    Records coarse metadata only — never the query or answer text.
    """
    if ctx is None or not settings.query_timing_log_enabled:
        return
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": ctx.mode,
        "stream": ctx.stream,
        "elapsed_ms": round(ctx.elapsed_s() * 1000),
        "first_token_ms": (
            round(first_token_s * 1000) if first_token_s is not None else None
        ),
        "n_hits": ctx.n_hits,
        "query_chars": ctx.query_chars,
        "answer_chars": answer_chars,
        "advisory": ctx.advisory,
        "coverage": ctx.coverage,
        "coverage_gate": ctx.coverage_gate_outcome,
        "scope_labels": ctx.scope_labels,
        "hits": [
            {
                "doc_id": hit.payload.doc_id,
                "section_path": hit.payload.section_path,
                "score": round(hit.score, 4),
            }
            for hit in ctx.hits
        ],
    }
    logger.info("query timing: %s", record)
    try:
        path = settings.query_timing_log_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:  # a logging failure must never break the answer
        logger.warning("Could not write query timing log to %s: %s", path, exc)
