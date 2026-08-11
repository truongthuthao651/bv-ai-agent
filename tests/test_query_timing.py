"""Response-time footer + metadata-only timing log (app/query_timing.py)."""

from __future__ import annotations

import json
import time

import pytest

from app.config.settings import settings
from app.query_timing import (
    TimingContext,
    format_elapsed,
    log_feedback,
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


def test_log_forces_refusal_mode_when_answer_text_is_refusal(
    tmp_path, monkeypatch
) -> None:
    from app.generation.prompts import REFUSAL_MESSAGE

    path = tmp_path / "query_timings.jsonl"
    monkeypatch.setattr(settings, "query_timing_log_enabled", True)
    monkeypatch.setattr(settings, "query_timing_log_path", path)

    log_query_timing(
        _ctx("hybrid", elapsed_s=5),
        answer_chars=len(REFUSAL_MESSAGE),
        answer_text=REFUSAL_MESSAGE,
    )

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["mode"] == "refusal"


def _stub_hit(doc_id: str = "d1", section_path: str = "Điều 5", score: float = 0.876):
    from app.models.schemas import DocType, Hit, QdrantPayload

    return Hit(
        point_id="p1",
        score=score,
        payload=QdrantPayload(
            doc_id=doc_id,
            doc_title="Bảo hiểm liên kết chung An Khang Như Ý",
            section_path=section_path,
            doc_type=DocType.POLICY,
            display_text="Quyền lợi tử vong: 100% STBH. Số tiền cụ thể là 500 triệu đồng.",
            chunk_index=0,
            ingested_at="2026-01-01T00:00:00+00:00",
        ),
    )


def test_log_records_hits_and_plan_flags_without_chunk_text(
    tmp_path, monkeypatch
) -> None:
    # ADM1 (2026-08-05 audit / Day 2): enough to reconstruct what a bad answer
    # saw (doc_id, section_path, score, and the guard flags that decided the
    # answer path) -- but the confidentiality bar from the original metadata-
    # only design must still hold: no chunk display_text, no query/answer text.
    path = tmp_path / "query_timings.jsonl"
    monkeypatch.setattr(settings, "query_timing_log_enabled", True)
    monkeypatch.setattr(settings, "query_timing_log_path", path)

    ctx = _ctx("grounded", elapsed_s=12)
    ctx.hits = [_stub_hit("d1", "Điều 5", 0.876), _stub_hit("d2", "Điều 6", 0.5)]
    ctx.advisory = True
    ctx.coverage = True
    ctx.coverage_gate_outcome = "regenerated"
    ctx.scope_labels = ["Bảo hiểm liên kết chung An Khang Như Ý"]

    log_query_timing(ctx, answer_chars=500)

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["hits"] == [
        {"doc_id": "d1", "section_path": "Điều 5", "score": 0.876},
        {"doc_id": "d2", "section_path": "Điều 6", "score": 0.5},
    ]
    assert record["advisory"] is True
    assert record["coverage"] is True
    assert record["coverage_gate"] == "regenerated"
    assert record["scope_labels"] == ["Bảo hiểm liên kết chung An Khang Như Ý"]
    # Confidentiality: the chunk's own content never reaches the log line.
    raw = path.read_text(encoding="utf-8")
    assert "STBH" not in raw
    assert "500 triệu" not in raw
    assert "display_text" not in raw
    assert "context_text" not in raw


def test_log_coverage_gate_defaults_to_none_for_non_coverage_turns(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "query_timings.jsonl"
    monkeypatch.setattr(settings, "query_timing_log_enabled", True)
    monkeypatch.setattr(settings, "query_timing_log_path", path)

    log_query_timing(_ctx("grounded"), answer_chars=10)

    record = json.loads(path.read_text(encoding="utf-8").strip())
    assert record["coverage_gate"] is None
    assert record["hits"] == []
    assert record["scope_labels"] == []


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


# --- P2-F2: thumbs-down feedback log (audit/REPORT.md) ---


def test_log_feedback_writes_feedback_jsonl(tmp_path, monkeypatch) -> None:
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(settings, "feedback_log_enabled", True)
    monkeypatch.setattr(settings, "feedback_log_path", path)

    log_feedback("chatcmpl-abc123", "sai_thong_tin")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["completion_id"] == "chatcmpl-abc123"
    assert record["reason"] == "sai_thong_tin"
    assert "ts" in record
    # The log contains only the written feedback, not copied query/answer text.
    assert set(record.keys()) == {"ts", "completion_id", "reason"}


def test_log_feedback_preserves_written_feedback(tmp_path, monkeypatch) -> None:
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(settings, "feedback_log_enabled", True)
    monkeypatch.setattr(settings, "feedback_log_path", path)

    log_feedback("chatcmpl-xyz", "Cần nêu rõ điều kiện loại trừ.")

    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["reason"] == "Cần nêu rõ điều kiện loại trừ."


def test_log_feedback_is_noop_when_disabled(tmp_path, monkeypatch) -> None:
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(settings, "feedback_log_enabled", False)
    monkeypatch.setattr(settings, "feedback_log_path", path)

    log_feedback("chatcmpl-abc123", "Câu trả lời cần chỉnh sửa.")

    assert not path.exists()
