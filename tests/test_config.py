"""Phase 1 smoke tests: config loads and the app imports cleanly."""

from __future__ import annotations


def test_settings_have_safe_defaults() -> None:
    from app.config.settings import get_settings

    s = get_settings()
    assert s.chat_model  # non-empty default
    assert s.qdrant_collection == "insurance_docs"
    assert s.retrieve_top_k >= s.rerank_top_k
    assert 0.0 < s.chunk_overlap_pct < 1.0


def test_cors_origins_parsed_from_csv(monkeypatch) -> None:
    from app.config.settings import Settings

    monkeypatch.setenv("CORS_ORIGINS", "http://a.local, http://b.local")
    s = Settings()
    assert s.cors_origins == ["http://a.local", "http://b.local"]


def test_app_imports_and_registers_health_route() -> None:
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/health" in paths


def test_admin_ui_served_at_root_without_shadowing_api_routes() -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    root = client.get("/")
    assert root.status_code == 200
    assert "text/html" in root.headers["content-type"]
    assert "Trợ lý AI" in root.text

    # The static mount is registered last specifically so it must not shadow
    # API routes registered earlier (see app/main.py).
    health = client.get("/health")
    assert health.status_code in (200, 503)  # reachable either way; not a 404
