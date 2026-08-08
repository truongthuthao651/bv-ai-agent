"""Per-employee accounts for the admin session gate (replaces the single
shared ``ADMIN_PASSWORD`` as the login check — see REDESIGN_PROMPT.md §7).

This is a deliberately small, self-hosted account store: SQLite (stdlib,
already gitignored under ``data/``, never committed) and PBKDF2-HMAC-SHA256
password hashing (stdlib ``hashlib``, no new dependency — reasonable for a
handful of internal accounts; would not be the right call at real
enterprise scale, but there is no SSO available to integrate against here).

There is no self-service signup and no email-sending: accounts are
provisioned directly (see ``scripts/seed_accounts.py``), not requested. Every
account's email must end in ``EMAIL_DOMAIN`` — a format check only, since
there is no corporate identity provider to actually verify domain membership
against; it keeps out typos and obviously-wrong addresses, nothing more.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass
from typing import Literal

from app.config.settings import settings

EMAIL_DOMAIN = "@baoviet.com"

Role = Literal["admin", "employee"]
_ROLES: tuple[Role, ...] = ("admin", "employee")

_PBKDF2_ITERATIONS = 260_000
_SALT_BYTES = 16


@dataclass(frozen=True)
class Account:
    email: str
    role: Role


def is_valid_domain(email: str) -> bool:
    return email.strip().lower().endswith(EMAIL_DOMAIN)


def _db_path():
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings.data_dir / "accounts.db"


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            email TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL
        )
        """
    )
    return con


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    ).hex()


def create_account(
    email: str, password: str, role: Role, *, overwrite: bool = False
) -> None:
    """Provision one account. Raises ``ValueError`` on a bad email/role/duplicate."""
    email = email.strip().lower()
    if not is_valid_domain(email):
        raise ValueError(f"Email phải thuộc miền {EMAIL_DOMAIN}: «{email}».")
    if role not in _ROLES:
        raise ValueError(f"Vai trò không hợp lệ: «{role}». Chọn admin hoặc employee.")
    salt = os.urandom(_SALT_BYTES)
    password_hash = _hash_password(password, salt)
    con = _connect()
    try:
        if not overwrite:
            existing = con.execute(
                "SELECT 1 FROM accounts WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                raise ValueError(
                    f"Tài khoản đã tồn tại: «{email}» (dùng overwrite=True để đổi)."
                )
        con.execute(
            "INSERT INTO accounts (email, role, password_hash, salt) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(email) DO UPDATE SET role = ?, password_hash = ?, salt = ?",
            (email, role, password_hash, salt.hex(), role, password_hash, salt.hex()),
        )
        con.commit()
    finally:
        con.close()


def authenticate(email: str, password: str) -> Account | None:
    """Constant-time-enough password check (PBKDF2 + hmac.compare_digest via ==
    on hex digests is not truly constant-time, but the hash computation itself
    dominates timing here — the same tradeoff PBKDF2-based systems commonly
    accept). Returns the account on success, else None (bad email, bad
    password, or no such account — same response either way, no enumeration
    hint)."""
    email = email.strip().lower()
    if not is_valid_domain(email):
        return None
    con = _connect()
    try:
        row = con.execute(
            "SELECT role, password_hash, salt FROM accounts WHERE email = ?", (email,)
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    role, password_hash, salt_hex = row
    if _hash_password(password, bytes.fromhex(salt_hex)) != password_hash:
        return None
    return Account(email=email, role=role)  # type: ignore[arg-type]


def any_accounts_exist() -> bool:
    con = _connect()
    try:
        return con.execute("SELECT 1 FROM accounts LIMIT 1").fetchone() is not None
    finally:
        con.close()


def list_accounts() -> list[Account]:
    """Emails + roles only — never password hashes. Used by the admin UI."""
    con = _connect()
    try:
        rows = con.execute("SELECT email, role FROM accounts ORDER BY email").fetchall()
    finally:
        con.close()
    return [Account(email=email, role=role) for email, role in rows]  # type: ignore[misc]
