"""Single-password session gate for the admin dashboard (port 8000).

Port 8000 is already meant to be reachable only from the manager's own
machine (``API_HOST=127.0.0.1`` by default — README), so this is
defense-in-depth for that one admin surface, not a multi-user account system:
the actual employee-facing product is Open WebUI, which already has its own
login (``WEBUI_AUTH``). One shared password, set via ``ADMIN_PASSWORD`` in
``.env``; no user database, no signup flow.

The session cookie is a signed ``expiry.hmac`` token (stdlib ``hmac`` +
``hashlib``, no new dependency) keyed on the admin password itself — anyone
who can forge a valid cookie already had to know the password, so this adds
no weaker link than the password check it follows.

When ``ADMIN_PASSWORD`` is unset the gate is a no-op (today's default,
open-on-loopback behavior) so existing dev/test setups keep working
unchanged; a startup warning is logged so this is a deliberate choice, not a
silently-forgotten one.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time

from app.config.settings import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "bv_admin_session"
SESSION_TTL_SECONDS = 60 * 60 * 12  # 12h — re-login roughly once a working day

# Paths reachable without a session (the admin-cookie gate, i.e. auth_enabled()
# below):
#  - /login, /logout: the auth flow itself (can't require auth to log in)
#  - /health: polled unauthenticated by scripts/run_native.sh and
#    scripts/healthcheck.sh (no cookie jar there)
#  - /v1: the OpenAI-compatible surface Open WebUI calls server-to-server.
#    NOT gated by the admin cookie (Open WebUI has no session for it) — instead
#    gated separately by check_shared_secret() below, opt-in via
#    API_SHARED_SECRET. Relying on WEBUI_AUTH alone is NOT enough: WEBUI_AUTH
#    protects the Open WebUI *browser* login, but /v1/chat/completions itself
#    has no independent check, so anyone who can reach the API host on the
#    network can call it directly, bypassing Open WebUI entirely (SEC1).
PUBLIC_PREFIXES = ("/login", "/logout", "/health", "/v1")

# Read-only, per-document source views (citation link targets). Employees reach
# these from Open WebUI (port 3000) without an admin session, so they must be
# public — but ONLY these two GET routes, never the /documents list or the
# DELETE route (which stay behind the admin gate). The doc_id segment is opaque
# and can't contain a slash, so the regex can't widen to those.
_PUBLIC_DOC_RE = re.compile(r"^/documents/[^/]+/(view|file)$")


def auth_enabled() -> bool:
    return bool(settings.admin_password)


def _sign(payload: str) -> str:
    key = settings.admin_password.encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def check_password(candidate: str) -> bool:
    """Constant-time compare against the configured admin password."""
    if not auth_enabled():
        return False
    return hmac.compare_digest(candidate, settings.admin_password)


def create_session_token() -> str:
    """A signed, expiring token to store in the session cookie."""
    expiry = str(int(time.time()) + SESSION_TTL_SECONDS)
    return f"{expiry}.{_sign(expiry)}"


def is_valid_session(token: str | None) -> bool:
    """True when ``token`` is a well-formed, correctly-signed, unexpired session."""
    if not auth_enabled() or not token:
        return False
    expiry_str, _, sig = token.partition(".")
    if not sig or not hmac.compare_digest(sig, _sign(expiry_str)):
        return False
    try:
        return int(expiry_str) > time.time()
    except ValueError:
        return False


def check_shared_secret(authorization_header: str | None) -> bool:
    """True when a request to /v1/* may proceed.

    No secret configured (``API_SHARED_SECRET`` empty, the default) means
    today's behavior: always true, unchanged. When a secret IS configured, the
    request must carry it as ``Authorization: Bearer <secret>`` — the header
    shape Open WebUI already sends its configured ``OPENAI_API_KEY`` as, so
    setting both to the same value is the entire migration (see README).
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
