"""Health endpoint.

`GET /health` checks the two backing services (Ollama and Qdrant) and reports a
per-service status so operators can tell WHAT is down, not just that something is.
All checks stay on the local machine — no external hosts. When Qdrant runs
embedded (``QDRANT_LOCAL_PATH`` set), there is no server to
ping; the check exercises the in-process client instead.
"""

from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.config.settings import settings

router = APIRouter(tags=["health"])


async def _ping(client: httpx.AsyncClient, url: str) -> dict[str, object]:
    """GET a service URL and classify the result as up/down with latency."""
    try:
        response = await client.get(url)
        response.raise_for_status()
        return {"status": "up", "http_status": response.status_code}
    except httpx.HTTPStatusError as exc:  # reachable but unhealthy
        return {"status": "down", "http_status": exc.response.status_code}
    except httpx.HTTPError as exc:  # unreachable / timeout
        return {"status": "down", "error": exc.__class__.__name__}


async def _check_embedded_qdrant() -> dict[str, object]:
    """Exercise the embedded (in-process) Qdrant client off the event loop."""

    def probe() -> None:
        from app.ingestion import indexer  # lazy: pulls in qdrant storage init

        indexer.get_client().get_collections()

    try:
        await asyncio.to_thread(probe)
        return {"status": "up", "mode": "embedded"}
    except Exception as exc:  # storage locked/corrupt — report, don't crash
        return {"status": "down", "mode": "embedded", "error": exc.__class__.__name__}


@router.get("/health")
async def health() -> JSONResponse:
    """Report overall + per-service health.

    Returns HTTP 200 when every dependency is reachable, otherwise 503 so that
    monitoring tools can act on it.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        ollama = await _ping(client, f"{settings.ollama_base_url}/api/tags")
        if settings.qdrant_local_path:
            qdrant = await _check_embedded_qdrant()
        else:
            # Qdrant's liveness probe; readyz/healthz both return 200 when serving.
            qdrant = await _ping(client, f"{settings.qdrant_url}/healthz")

    services = {"ollama": ollama, "qdrant": qdrant}
    healthy = all(svc["status"] == "up" for svc in services.values())

    body = {
        "status": "ok" if healthy else "degraded",
        "services": services,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
