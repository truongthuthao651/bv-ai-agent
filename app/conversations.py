"""Per-user conversation storage — private to each signed-in account.

Conversations are keyed by (email, id). There is intentionally no admin
list-all endpoint: admins manage documents and metrics, not employee chat
threads (privacy requirement). Only the owning account can read/write/delete
its own rows via app/api/conversations.py.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from app.config.settings import settings


@dataclass
class Conversation:
    id: str
    title: str
    custom_title: str | None
    messages: list[dict[str, Any]]
    updated_at: int


def _db_path():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "conversations.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            email TEXT NOT NULL,
            id TEXT NOT NULL,
            title TEXT NOT NULL,
            custom_title TEXT,
            messages_json TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            PRIMARY KEY (email, id)
        )
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_conversations_email_updated "
        "ON conversations (email, updated_at DESC)"
    )
    return con


def _row_to_conv(row: tuple) -> Conversation:
    _email, cid, title, custom_title, messages_json, updated_at = row
    try:
        messages = json.loads(messages_json)
        if not isinstance(messages, list):
            messages = []
    except json.JSONDecodeError:
        messages = []
    return Conversation(
        id=cid,
        title=title,
        custom_title=custom_title or None,
        messages=messages,
        updated_at=int(updated_at),
    )


def list_conversations(email: str) -> list[Conversation]:
    email = email.strip().lower()
    con = _connect()
    try:
        rows = con.execute(
            "SELECT email, id, title, custom_title, messages_json, updated_at "
            "FROM conversations WHERE email = ? ORDER BY updated_at DESC",
            (email,),
        ).fetchall()
    finally:
        con.close()
    return [_row_to_conv(r) for r in rows]


def get_conversation(email: str, conv_id: str) -> Conversation | None:
    email = email.strip().lower()
    con = _connect()
    try:
        row = con.execute(
            "SELECT email, id, title, custom_title, messages_json, updated_at "
            "FROM conversations WHERE email = ? AND id = ?",
            (email, conv_id),
        ).fetchone()
    finally:
        con.close()
    return _row_to_conv(row) if row else None


def upsert_conversation(
    email: str,
    conv_id: str,
    *,
    title: str,
    custom_title: str | None,
    messages: list[dict[str, Any]],
    updated_at: int,
) -> Conversation:
    email = email.strip().lower()
    messages_json = json.dumps(messages, ensure_ascii=False)
    con = _connect()
    try:
        con.execute(
            """
            INSERT INTO conversations (email, id, title, custom_title, messages_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(email, id) DO UPDATE SET
                title = excluded.title,
                custom_title = excluded.custom_title,
                messages_json = excluded.messages_json,
                updated_at = excluded.updated_at
            """,
            (email, conv_id, title, custom_title, messages_json, updated_at),
        )
        con.commit()
    finally:
        con.close()
    return Conversation(
        id=conv_id,
        title=title,
        custom_title=custom_title,
        messages=messages,
        updated_at=updated_at,
    )


def delete_conversation(email: str, conv_id: str) -> bool:
    email = email.strip().lower()
    con = _connect()
    try:
        cur = con.execute(
            "DELETE FROM conversations WHERE email = ? AND id = ?",
            (email, conv_id),
        )
        con.commit()
        return cur.rowcount > 0
    finally:
        con.close()


def delete_all_conversations(email: str) -> int:
    email = email.strip().lower()
    con = _connect()
    try:
        cur = con.execute("DELETE FROM conversations WHERE email = ?", (email,))
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def replace_all_conversations(email: str, items: list[Conversation]) -> None:
    """Bulk replace — used by sync endpoint after client migration."""
    email = email.strip().lower()
    con = _connect()
    try:
        con.execute("DELETE FROM conversations WHERE email = ?", (email,))
        for conv in items:
            con.execute(
                """
                INSERT INTO conversations (email, id, title, custom_title, messages_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    conv.id,
                    conv.title,
                    conv.custom_title,
                    json.dumps(conv.messages, ensure_ascii=False),
                    conv.updated_at,
                ),
            )
        con.commit()
    finally:
        con.close()
