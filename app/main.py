"""FastAPI entrypoint.

Wires up routers and application lifespan (model warmup): ``/health``, ``/ingest``
+ ``/documents`` (Markdown/DOCX/XLSX/PDF/glossary), and the OpenAI-compatible
``/v1/chat/completions``. Scanned-image OCR arrives with the OCR increment.

Also serves the React frontend (built by ``frontend/``, output committed to
``app/static/dist/``): the public landing page at ``/``, the admin console at
``/admin`` (upload/edit/delete documents, metrics; admin role only), and the
chat UI at ``/chat`` (any signed-in account). The build step runs on the dev
machine only; the deployment machine serves the committed static output and
never runs npm.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app import auth
from app.api import (
    admin_ops,
    chat,
    chat_ui,
    conversations,
    health,
    ingest,
    login,
    metrics,
)
from app.config.settings import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("bv-ai-agent")


async def _warmup() -> None:
    """Best-effort pre-load of the lazily-initialized, slow-to-start pieces.

    Ensures the Qdrant collection exists and loads the bge-m3 embedder, the
    reranker, and the Ollama chat model up front so the first real request isn't
    cold. Each step is isolated in its own ``try`` and blocking work is pushed to
    a threadpool: a missing service or model weights degrades to a logged warning
    rather than a failed startup (e.g. on a dev box without weights downloaded).
    """
    # Imported here (not at module load) so importing app.main stays cheap and
    # free of the heavy embedding/reranking dependencies.
    from app.generation import generator
    from app.ingestion import indexer
    from app.retrieval import reranker

    steps = (
        ("Qdrant collection", indexer.ensure_collection),
        ("bge-m3 embedder", indexer.get_embedder),
        ("reranker", reranker.get_reranker),
        ("Ollama chat model", generator.preload_model),
    )
    for label, fn in steps:
        try:
            await run_in_threadpool(fn)
            logger.info("Warmup: %s ready", label)
        except Exception as exc:  # noqa: BLE001 - warmup must never break startup
            logger.warning(
                "Warmup: %s unavailable (%s); will load on demand", label, exc
            )


def _citation_base_is_loopback() -> bool:
    """True when citation links would only resolve on this machine.

    ``format_sources`` builds citation links from ``API_PUBLIC_BASE_URL``. When
    that points at loopback (the default), a link opens the *reader's own*
    localhost — fine on the server, dead for an employee on another LAN machine.
    """
    host = urlparse(settings.api_public_base_url).hostname or ""
    return host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: optional warmup on startup (see ``_warmup``)."""
    logger.info("Starting bv-ai-agent API (chat_model=%s)", settings.chat_model)
    if not auth.auth_enabled():
        logger.warning(
            "No accounts provisioned: /admin and /chat are reachable without "
            "login. Run scripts/seed_accounts.py to create one."
        )
    if not settings.session_secret_key:
        logger.warning(
            "SESSION_SECRET_KEY is not set: a random key was generated for this "
            "process only, so every session is invalidated on restart. Set a fixed "
            "value in .env for sessions to persist across restarts."
        )
    if _citation_base_is_loopback():
        logger.warning(
            "API_PUBLIC_BASE_URL is loopback (%s): citation links in answers open "
            "the reader's OWN localhost, so they only work when browsing FROM this "
            "server. For employees on the LAN, set API_PUBLIC_BASE_URL to this "
            "machine's LAN address and expose the read-only /documents/{id}/view "
            "and /file routes there — /admin stays protected by the account login "
            "regardless. See README (Liên kết trích dẫn cho người dùng trong mạng LAN).",
            settings.api_public_base_url,
        )
    if settings.api_host == "0.0.0.0" and not settings.api_shared_secret:
        logger.warning(
            "API_HOST=0.0.0.0 with API_SHARED_SECRET unset: /v1/chat/completions "
            "is reachable and UNAUTHENTICATED from anywhere on the LAN by anyone "
            "who never even loaded /chat (a signed-in /chat session is always "
            "accepted regardless of this setting — see admin_session_gate). Set "
            "API_SHARED_SECRET to a random value, or restrict LAN access with a "
            "firewall rule, to close that gap for direct API callers. "
            "See README (Liên kết trích dẫn cho người dùng trong mạng LAN)."
        )
    if settings.warmup_on_startup:
        await _warmup()
    yield
    logger.info("Shutting down bv-ai-agent API")


app = FastAPI(
    title="Trợ lý AI Bảo Việt Life — Local RAG API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.middleware("http")
async def admin_session_gate(request: Request, call_next):
    """Require a valid account session for everything except the public
    surface, and restrict /admin to the "admin" role (§ RBAC).

    Public surface (app/auth.py PUBLIC_PREFIXES): /health, /login, /logout,
    the public landing page, static assets, and the public doc-view routes.
    A no-op when no account has been provisioned yet (auth.auth_enabled()).

    /v1 accepts a valid account session (same-origin /chat calls) OR
    API_SHARED_SECRET bearer token when configured.
    """
    path = request.url.path
    # Attached for every request (gated or not) so downstream endpoints can
    # read "who is this" via auth.current_account() without re-parsing the
    # cookie — used by auth.require_admin() and the /admin role check below.
    request.state.account = auth.is_valid_session(request.cookies.get(auth.COOKIE_NAME))

    if path == "/v1" or path.startswith("/v1/"):
        if (
            auth.check_shared_secret(request.headers.get("authorization"))
            or request.state.account is not None
        ):
            return await call_next(request)
        return JSONResponse(
            status_code=401, content={"detail": "Missing or invalid API key."}
        )

    if not auth.auth_enabled() or auth.is_public_path(path):
        return await call_next(request)

    account = request.state.account
    if account is None:
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url=f"/login?next={path}", status_code=303)
        return JSONResponse(status_code=401, content={"detail": "Yêu cầu đăng nhập."})

    # RBAC: /admin is admin-only. Employees are signed in (they can use /chat)
    # but sent back there rather than shown an error for a page they'll never
    # but sent back there rather than shown an error for a page they can't use.
    if (path == "/admin" or path.startswith("/admin/")) and account.role != "admin":
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url="/chat/", status_code=303)
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Chỉ quản trị viên (admin) mới truy cập được trang này."
            },
        )

    return await call_next(request)


app.include_router(health.router)
app.include_router(chat.router)
app.include_router(chat_ui.router)
app.include_router(ingest.router)
app.include_router(login.router)
app.include_router(metrics.router)
app.include_router(conversations.router)
app.include_router(admin_ops.router)

_STATIC_DIR = Path(__file__).parent / "static"
_TOKENS_DIR = Path(__file__).parent.parent / "frontend" / "src" / "tokens"

# Static content served independently of the Vite build, each vendored
# separately from the design system and reachable without a session (see
# app/auth.py PUBLIC_PREFIXES) since none of it is business data — only code,
# styles, fonts, and brand images:
#   /fonts   self-hosted Inter woff2 (public/fonts symlink -> app/static/fonts)
#   /assets  brand images + favicons (public/assets symlink -> app/static/assets),
#            a DIFFERENT path from Vite's own JS/CSS output (see vite.config.js
#            assetsDir: "app-assets") so the two can't collide
#   /tokens  the raw frontend token CSS, loaded directly by
#            app/templates/login.html. Keep this as a real source directory:
#            Git for Windows checks out Unix symlinks as plain text files.
app.mount("/fonts", StaticFiles(directory=_STATIC_DIR / "fonts"), name="fonts")
app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="brand-assets")
app.mount("/tokens", StaticFiles(directory=_TOKENS_DIR), name="tokens")

# Mounted last so it only catches paths not matched by an API route or the
# mounts above (e.g. "/", "/admin/", "/app-assets/...") and doesn't shadow
# /health, /ingest, etc. Vite's two-page build puts the public landing page at
# dist/index.html ("/") and the gated admin console at dist/admin/index.html
# ("/admin/") — see app/auth.py for which of those the session gate protects.
app.mount(
    "/",
    StaticFiles(directory=_STATIC_DIR / "dist", html=True),
    name="web-ui",
)
