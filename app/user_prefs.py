"""Per-account profile preferences stored server-side.

Only non-sensitive personalization (display name, avatar swatch) — theme stays
client-local because it is device-specific.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.config.settings import settings

ALLOWED_AVATAR_SWATCHES = frozenset({"accent", "gold", "success", "navy"})


@dataclass
class UserPrefs:
    display_name: str | None = None
    avatar_swatch: str | None = None


def _db_path():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "user_prefs.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS user_prefs (
            email TEXT PRIMARY KEY,
            display_name TEXT,
            avatar_swatch TEXT
        )
        """
    )
    return con


def get_prefs(email: str) -> UserPrefs:
    email = email.strip().lower()
    con = _connect()
    try:
        row = con.execute(
            "SELECT display_name, avatar_swatch FROM user_prefs WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return UserPrefs()
    display_name, avatar_swatch = row
    return UserPrefs(
        display_name=display_name or None,
        avatar_swatch=avatar_swatch
        if avatar_swatch in ALLOWED_AVATAR_SWATCHES
        else None,
    )


def update_prefs(
    email: str,
    *,
    display_name: str | None = None,
    avatar_swatch: str | None = None,
) -> UserPrefs:
    """Patch prefs for one account. ``None`` for a field means leave unchanged."""
    email = email.strip().lower()
    current = get_prefs(email)
    next_name = current.display_name
    if display_name is not None:
        stripped = display_name.strip()
        if not stripped:
            raise ValueError("Tên hiển thị không được để trống.")
        next_name = stripped
    next_swatch = current.avatar_swatch if avatar_swatch is None else avatar_swatch
    if next_swatch is not None and next_swatch not in ALLOWED_AVATAR_SWATCHES:
        raise ValueError("Màu avatar không hợp lệ.")
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO user_prefs (email, display_name, avatar_swatch)
            VALUES (?, ?, ?)
            ON CONFLICT(email) DO UPDATE SET
                display_name = excluded.display_name,
                avatar_swatch = excluded.avatar_swatch
            """,
            (email, next_name, next_swatch),
        )
        con.commit()
    finally:
        con.close()
    return UserPrefs(display_name=next_name, avatar_swatch=next_swatch)
