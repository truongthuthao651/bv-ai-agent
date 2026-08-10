"""Asia/Ho_Chi_Minh timestamp helpers."""

from __future__ import annotations

from app.vn_time import parse_ts, to_vn


def test_parse_ts_accepts_z_suffix() -> None:
    ts = parse_ts("2026-08-09T12:00:00Z")
    assert ts is not None
    assert ts.tzinfo is not None


def test_to_vn_converts_utc_to_local_date() -> None:
    ts = parse_ts("2026-08-09T17:00:00+00:00")
    assert ts is not None
    vn = to_vn(ts)
    assert vn.date().isoformat() == "2026-08-10"
    assert vn.hour == 0
