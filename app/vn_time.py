"""Vietnam (Asia/Ho_Chi_Minh, UTC+7) timestamps for logs, metrics, and admin UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def now_vn() -> datetime:
    return datetime.now(VN_TZ)


def now_vn_iso() -> str:
    return now_vn().isoformat()


def parse_ts(raw: str) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def to_vn(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(VN_TZ)


def since_hours_ago(hours: float) -> datetime:
    return now_vn() - timedelta(hours=hours)
