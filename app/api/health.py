"""Health endpoint.

`GET /health` pings the two backing services (Ollama and Qdrant) and reports a
per-service status so operators can tell WHAT is down, not just that something is.
All network calls stay within the local Docker network — no external hosts.
"""

from __future__ import annotations

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


@router.get("/health")
async def health() -> JSONResponse:
    """Report overall + per-service health.

    Returns HTTP 200 when every dependency is reachable, otherwise 503 so that
    Docker/orchestration health checks can act on it.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        ollama = await _ping(client, f"{settings.ollama_base_url}/api/tags")
        # Qdrant's liveness probe; readyz/healthz both return 200 when serving.
        qdrant = await _ping(client, f"{settings.qdrant_url}/healthz")

    services = {"ollama": ollama, "qdrant": qdrant}
    healthy = all(svc["status"] == "up" for svc in services.values())

    body = {
        "status": "ok" if healthy else "degraded",
        "services": services,
    }
    return JSONResponse(status_code=200 if healthy else 503, content=body)
