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
