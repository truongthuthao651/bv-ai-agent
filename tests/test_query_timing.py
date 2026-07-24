"""Response-time footer + metadata-only timing log (app/query_timing.py)."""

from __future__ import annotations

import json
import time

import pytest

from app.config.settings import settings
from app.query_timing import (
    TimingContext,
    format_elapsed,
    log_query_timing,
    response_time_footer,
)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, "0s"),
        (0.4, "0s"),
        (1, "1s"),
        (45, "45s"),
        (59.6, "1m00s"),
        (60, "1m00s"),
        (115, "1m55s"),
        (600, "10m00s"),
    ],
)
def test_format_elapsed(seconds: float, expected: str) -> None:
    assert format_elapsed(seconds) == expected


def test_format_elapsed_never_negative() -> None:
    # Monotonic clock skew must not produce a "-1s" footer.
    assert format_elapsed(-3) == "0s"


def _ctx(mode: str = "grounded", *, elapsed_s: float = 115.0) -> TimingContext:
    # Backdate started_at so elapsed_s() reports a fixed, deterministic value.
    return TimingContext(
        started_at=time.perf_counter() - elapsed_s,
        mode=mode,
        n_hits=3,
        query_chars=42,
    )


def test_footer_present_when_enabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "show_response_time", True)
    footer = response_time_footer(_ctx(elapsed_s=115))
    assert footer.strip() == "_⏱ Thời gian trả lời: 1m55s_"


def test_footer_absent_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(settings, "show_response_time", True)
    assert response_time_footer(None) == ""  # meta-tasks pass no context


def test_footer_absent_when_setting_off(monkeypatch) -> None:
    monkeypatch.setattr(settings, "show_response_time", False)
    assert response_time_footer(_ctx()) == ""


def test_log_writes_metadata_only_jsonl(tmp_path, monkeypatch) -> None:
    path = tmp_path / "query_timings.jsonl"
    monkeypatch.setattr(settings, "query_timing_log_enabled", True)
    monkeypatch.setattr(settings, "query_timing_log_path", path)

    log_query_timing(
        _ctx("advisory", elapsed_s=90), answer_chars=1234, first_token_s=12
    )

    line = path.read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["mode"] == "advisory"
    assert record["n_hits"] == 3
    assert record["query_chars"] == 42
    assert record["answer_chars"] == 1234
    assert record["first_token_ms"] == 12000
    assert 89_000 <= record["elapsed_ms"] <= 91_000
    # No query or answer TEXT is ever recorded (confidentiality).
    assert "query" not in record and "answer" not in record
    assert "text" not in line.lower()


def test_log_is_noop_when_disabled(tmp_path, monkeypatch) -> None:
    path = tmp_path / "query_timings.jsonl"
    monkeypatch.setattr(settings, "query_timing_log_enabled", False)
    monkeypatch.setattr(settings, "query_timing_log_path", path)
    log_query_timing(_ctx(), answer_chars=10)
    assert not path.exists()


def test_log_is_noop_without_context(tmp_path, monkeypatch) -> None:
    path = tmp_path / "query_timings.jsonl"
    monkeypatch.setattr(settings, "query_timing_log_enabled", True)
    monkeypatch.setattr(settings, "query_timing_log_path", path)
    log_query_timing(None, answer_chars=10)  # e.g. a meta-task
    assert not path.exists()


def test_static_stream_appends_footer_when_timing_given(monkeypatch) -> None:
    import asyncio

    from app.generation.generator import stream_static_answer

    monkeypatch.setattr(settings, "show_response_time", True)
    monkeypatch.setattr(settings, "query_timing_log_enabled", False)

    async def collect(timing):
        return [c async for c in stream_static_answer("Xin chào.", timing=timing)]

    # With a context the footer is streamed as a content delta before [DONE].
    chunks = asyncio.run(collect(_ctx(elapsed_s=115)))
    body = "".join(
        json.loads(c.removeprefix("data: "))["choices"][0]["delta"].get("content", "")
        for c in chunks
        if c.strip() and c.strip() != "data: [DONE]"
    )
    assert body == "Xin chào.\n\n_⏱ Thời gian trả lời: 1m55s_"

    # Meta-task style (no context) streams the bare text, no footer.
    plain = asyncio.run(collect(None))
    plain_body = "".join(
        json.loads(c.removeprefix("data: "))["choices"][0]["delta"].get("content", "")
        for c in plain
        if c.strip() and c.strip() != "data: [DONE]"
    )
    assert plain_body == "Xin chào."
