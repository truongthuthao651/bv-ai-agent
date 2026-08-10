"""GET /metrics/summary (app/api/metrics.py) — Day 4 / 2026-08-05 audit.

summarize() is pure (unit-tested without I/O); the endpoint itself is
smoke-tested against a real JSONL file via TestClient.
"""

from __future__ import annotations

import json

from app.api.metrics import _percentile, _read_records, summarize


def _rec(
    mode: str, elapsed_ms: int, n_hits: int, ts: str = "2026-08-05T10:00:00+00:00"
):
    return {"ts": ts, "mode": mode, "elapsed_ms": elapsed_ms, "n_hits": n_hits}


def test_percentile_empty_is_none() -> None:
    assert _percentile([], 50) is None


def test_percentile_p50_and_p95() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert _percentile(values, 50) == 30.0
    assert _percentile(values, 95) == 50.0


def test_summarize_empty_records() -> None:
    summary = summarize([], window_hours=24.0)
    assert summary.n_requests == 0
    assert summary.refusal_rate is None
    assert summary.elapsed_ms_p50 is None
    assert summary.mode_breakdown.grounded == 0


def test_summarize_mode_breakdown_and_refusal_rate() -> None:
    records = [
        _rec("grounded", 5000, 3),
        _rec("grounded", 6000, 5),
        _rec("advisory", 7000, 4),
        _rec("hybrid", 2000, 0),
        _rec("refusal", 1000, 0),
    ]
    summary = summarize(records, window_hours=24.0)
    assert summary.n_requests == 5
    assert summary.mode_breakdown.grounded == 2
    assert summary.mode_breakdown.advisory == 1
    assert summary.mode_breakdown.hybrid == 1
    assert summary.mode_breakdown.refusal == 1
    assert summary.refusal_rate == 0.2


def test_summarize_unknown_mode_counted_as_other() -> None:
    records = [_rec("meta", 100, 0), _rec("clarification", 200, 0)]
    summary = summarize(records, window_hours=None)
    assert summary.mode_breakdown.other == 2
    assert summary.mode_breakdown.grounded == 0


def test_summarize_elapsed_and_hits_stats() -> None:
    records = [_rec("grounded", ms, h) for ms, h in [(1000, 1), (2000, 3), (3000, 5)]]
    summary = summarize(records, window_hours=24.0)
    assert summary.elapsed_ms_p50 == 2000
    assert summary.n_hits_mean == 3.0
    assert summary.n_hits_max == 5


def test_summarize_ignores_records_missing_numeric_fields() -> None:
    # e.g. a "meta"/"clarification" record legitimately has no n_hits recorded.
    records = [{"ts": "2026-08-05T10:00:00+00:00", "mode": "meta"}]
    summary = summarize(records, window_hours=24.0)
    assert summary.n_requests == 1
    assert summary.elapsed_ms_p50 is None
    assert summary.n_hits_mean is None


def test_read_records_skips_corrupt_last_line(tmp_path, monkeypatch) -> None:
    from app.config.settings import settings

    path = tmp_path / "query_timings.jsonl"
    path.write_text(
        json.dumps(_rec("grounded", 1000, 2)) + "\n" + '{"ts": "2026-08-05T1',
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "query_timing_log_path", path)
    records = _read_records(since=None)
    assert len(records) == 1


def test_read_records_missing_file_returns_empty(tmp_path, monkeypatch) -> None:
    from app.config.settings import settings

    monkeypatch.setattr(settings, "query_timing_log_path", tmp_path / "nope.jsonl")
    assert _read_records(since=None) == []


def test_read_records_time_window_filters_old_entries(tmp_path, monkeypatch) -> None:
    from app.config.settings import settings
    from app.vn_time import now_vn_iso, since_hours_ago

    path = tmp_path / "query_timings.jsonl"
    old = _rec("grounded", 1000, 1, ts="2020-01-01T00:00:00+00:00")
    recent = _rec("grounded", 2000, 2, ts=now_vn_iso())
    path.write_text(
        json.dumps(old) + "\n" + json.dumps(recent) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(settings, "query_timing_log_path", path)

    records = _read_records(since=since_hours_ago(1))
    assert len(records) == 1
    assert records[0]["n_hits"] == 2


def test_daily_volume_and_heatmap_use_vn_timezone() -> None:
    from app.api.metrics import _daily_volume, _heatmap

    # 2026-08-09 17:00 UTC = 2026-08-10 00:00 in Vietnam
    records = [_rec("grounded", 1000, 1, ts="2026-08-09T17:00:00+00:00")]
    daily = _daily_volume(records)
    assert daily[0].date == "2026-08-10"
    heat = _heatmap(records)
    cell = next(c for c in heat if c.count == 1)
    assert cell.hour == 0


def test_metrics_summary_endpoint_live(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.config.settings import settings
    from app.main import app

    path = tmp_path / "query_timings.jsonl"
    path.write_text(
        json.dumps(_rec("grounded", 1000, 3))
        + "\n"
        + json.dumps(_rec("refusal", 500, 0)),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "query_timing_log_path", path)
    monkeypatch.setattr(settings, "warmup_on_startup", False)

    with TestClient(app) as client:
        resp = client.get("/metrics/summary?hours=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body["n_requests"] == 2
    assert body["mode_breakdown"]["refusal"] == 1
    assert body["refusal_rate"] == 0.5
