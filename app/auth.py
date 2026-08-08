"""Per-account session gate for /admin and /chat (port 8000).

Everything the employee-facing product needs — chat AND administration —
now lives behind this one gate (Open WebUI has been retired; there is no
second, separate login anymore). It USED TO be one shared ``ADMIN_PASSWORD``;
per REDESIGN_PROMPT.md §7 (no reachable internal SSO), it now checks
per-account email+password against ``app/accounts.py`` instead — every
account email must end in ``accounts.EMAIL_DOMAIN``. Accounts are
provisioned directly (``scripts/seed_accounts.py``); there is still no
self-service signup. Role gates WHICH surfaces an account reaches: any
signed-in account can use ``/chat``; only ``role="admin"`` can reach
``/admin`` or its mutating endpoints (``app.main.admin_session_gate``,
``require_admin``).

The session cookie is a signed ``email|role|expiry.hmac`` token (stdlib
``hmac`` + ``hashlib``, no new dependency), keyed on ``SESSION_SECRET_KEY``
rather than a password now that there is more than one — see
``app.config.settings.session_secret_key``.

When no account has been provisioned yet, the gate is a no-op (today's
fresh-install default, open-on-loopback behavior) so existing dev/test setups
keep working unchanged; a startup warning is logged so this is a deliberate
state, not a silently-forgotten one.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time

from fastapi import HTTPException, Request

from app import accounts
from app.accounts import Account
from app.config.settings import settings

logger = logging.getLogger(__name__)

# Generated once per process if SESSION_SECRET_KEY is unset in .env (see the
# startup warning in app/main.py) — sessions won't survive a restart in that
# case, but the gate still works correctly within one run.
_fallback_secret_key = secrets.token_hex(32)

COOKIE_NAME = "bv_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 12  # 12h — re-login roughly once a working day

# Paths reachable without a session (the admin-cookie gate, i.e. auth_enabled()
# below). Note /v1 is deliberately NOT here — see app.main.admin_session_gate,
# which gives it its own combined check (valid session OR API_SHARED_SECRET)
# rather than leaving it open by default:
#  - /login, /logout: the auth flow itself (can't require auth to log in)
#  - /health: polled unauthenticated by scripts/run_native.sh and
#    scripts/healthcheck.sh (no cookie jar there)
#  - "/" (exact match only — see is_public_path): the public landing page
#    (REDESIGN_PROMPT.md §6). The admin console moved to "/admin" precisely so
#    it could stay gated once "/" became public; "/admin" is deliberately
#    NOT in this list.
#  - /assets, /app-assets, /fonts, /tokens: static code/styles/fonts/images,
#    never business data. These must be public or the public landing page
#    (and the restyled /login, which loads /tokens directly) can't render
#    when an account is provisioned — the admin bundle's own JS/CSS live under
#    /app-assets too, but shipping compiled UI code publicly is normal (the
#    security boundary is the gated data endpoints below, not the JS itself).
PUBLIC_PREFIXES = (
    "/login",
    "/logout",
    "/health",
    "/",
    "/assets",
    "/app-assets",
    "/fonts",
    "/tokens",
)

# Read-only, per-document source views (citation link targets). Employees reach
# these from /chat without an admin session, so they must be
# public — but ONLY these two GET routes, never the /documents list or the
# DELETE route (which stay behind the admin gate). The doc_id segment is opaque
# and can't contain a slash, so the regex can't widen to those.
_PUBLIC_DOC_RE = re.compile(r"^/documents/[^/]+/(view|file)$")


def auth_enabled() -> bool:
    if settings.admin_password:
        logger.warning(
            "ADMIN_PASSWORD is set but no longer used — the admin gate now "
            "checks per-account email+password. See scripts/seed_accounts.py."
        )
    return accounts.any_accounts_exist()


def _signing_key() -> bytes:
    return (settings.session_secret_key or _fallback_secret_key).encode("utf-8")


def _sign(payload: str) -> str:
    return hmac.new(_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(account: Account) -> str:
    """A signed, expiring token to store in the session cookie."""
    expiry = str(int(time.time()) + SESSION_TTL_SECONDS)
    payload = f"{account.email}|{account.role}|{expiry}"
    return f"{payload}.{_sign(payload)}"


def is_valid_session(token: str | None) -> Account | None:
    """The signed-in ``Account`` for a well-formed, correctly-signed, unexpired
    session token, or ``None``. Never trusts the email/role inside the token
    without re-verifying the signature first — those fields ride along in the
    cookie, but only ``_sign`` (keyed on ``SESSION_SECRET_KEY``) makes them
    authoritative rather than user-editable.
    """
    if not auth_enabled() or not token:
        return None
    payload, _, sig = token.rpartition(".")
    if not sig or not payload or not hmac.compare_digest(sig, _sign(payload)):
        return None
    email, _, rest = payload.partition("|")
    role, _, expiry_str = rest.partition("|")
    if role not in ("admin", "employee"):
        return None
    try:
        if int(expiry_str) <= time.time():
            return None
    except ValueError:
        return None
    return Account(email=email, role=role)  # type: ignore[arg-type]


def check_shared_secret(authorization_header: str | None) -> bool:
    """True when a request to /v1/* may proceed on shared-secret grounds alone.

    ``/chat`` never needs this — its same-origin fetch calls already carry
    the account session cookie, which app.main.admin_session_gate accepts for
    /v1 directly. This exists for any OTHER direct caller of the API (a
    script, a future integration): no secret configured (``API_SHARED_SECRET``
    empty, the default) means always true; when a secret IS configured, the
    request must carry it as ``Authorization: Bearer <secret>``.
    """
    secret = settings.api_shared_secret
    if not secret:
        return True
    if not authorization_header or not authorization_header.startswith("Bearer "):
        return False
    token = authorization_header.removeprefix("Bearer ").strip()
    return hmac.compare_digest(token, secret)


def is_public_path(path: str) -> bool:
    if _PUBLIC_DOC_RE.match(path):
        return True
    return any(
        path == prefix or path.startswith(prefix + "/") for prefix in PUBLIC_PREFIXES
    )


def current_account(request: Request) -> Account | None:
    """The signed-in account for this request, if any.

    Set on ``request.state`` by ``admin_session_gate`` (app/main.py) for every
    request, gated or not — reading it back here (rather than re-parsing the
    cookie) keeps a single source of truth for "who is this" per request.
    """
    return getattr(request.state, "account", None)


def require_admin(request: Request) -> None:
    """FastAPI dependency: 403s a mutating endpoint for a non-admin account.

    A no-op when the gate itself is disabled (no accounts provisioned yet) —
    consistent with every other endpoint staying open in that fresh-install
    state. When the gate IS enabled, ``admin_session_gate`` has already
    guaranteed a valid account reached this point (anything else was
    redirected/401'd earlier), so this only ever needs to check the role.
    """
    if not auth_enabled():
        return
    account = current_account(request)
    if account is None or account.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Chỉ quản trị viên (admin) mới có thể thực hiện thao tác này.",
        )
