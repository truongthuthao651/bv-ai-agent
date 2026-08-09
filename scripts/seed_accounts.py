#!/usr/bin/env python
"""Provision an account (app/accounts.py).

Admin accounts must be created by an operator — employees self-register at
/login ("Tạo tài khoản") with any @baoviet.com email.

    .venv/bin/python scripts/seed_accounts.py admin@baoviet.com S0meP@ss admin
    .venv/bin/python scripts/seed_accounts.py employee@baoviet.com S0meP@ss employee

Email must end in app.accounts.EMAIL_DOMAIN (a format check only — there is
no corporate identity provider to verify domain membership against).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import accounts  # noqa: E402


def main() -> int:
    if len(sys.argv) != 4:
        print(
            f"Usage: {sys.argv[0]} <email> <password> <admin|employee>",
            file=sys.stderr,
        )
        return 1
    email, password, role = sys.argv[1], sys.argv[2], sys.argv[3]
    try:
        accounts.create_account(email, password, role, overwrite=True)  # type: ignore[arg-type]
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Đã tạo/cập nhật tài khoản: {email} ({role})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
