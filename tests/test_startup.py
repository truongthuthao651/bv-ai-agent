"""Startup warmup: best-effort, ordered, and never fatal.

Exercises ``app.main._warmup`` and the lifespan gating with injected fakes — no
real models, Qdrant, or Ollama are loaded.
"""

from __future__ import annotations

import asyncio

import app.main as main_module
from app.generation import generator
from app.ingestion import indexer
from app.retrieval import reranker


def test_warmup_runs_each_step_in_order(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        indexer, "ensure_collection", lambda: calls.append("collection")
    )
    monkeypatch.setattr(indexer, "get_embedder", lambda: calls.append("embedder"))
    monkeypatch.setattr(reranker, "get_reranker", lambda: calls.append("reranker"))
    monkeypatch.setattr(generator, "preload_model", lambda: calls.append("ollama"))

    asyncio.run(main_module._warmup())

    assert calls == ["collection", "embedder", "reranker", "ollama"]


def test_warmup_swallows_every_failure(monkeypatch) -> None:
    def boom() -> None:
        raise RuntimeError("service down")

    monkeypatch.setattr(indexer, "ensure_collection", boom)
    monkeypatch.setattr(indexer, "get_embedder", boom)
    monkeypatch.setattr(reranker, "get_reranker", boom)
    monkeypatch.setattr(generator, "preload_model", boom)

    # A failing dependency must degrade to a logged warning, not crash startup.
    asyncio.run(main_module._warmup())


def test_lifespan_skips_warmup_when_disabled(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.config.settings import settings

    called = False

    async def fake_warmup() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(main_module, "_warmup", fake_warmup)
    monkeypatch.setattr(settings, "warmup_on_startup", False)

    with TestClient(main_module.app):
        pass

    assert called is False


def test_lifespan_runs_warmup_when_enabled(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.config.settings import settings

    called = False

    async def fake_warmup() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(main_module, "_warmup", fake_warmup)
    monkeypatch.setattr(settings, "warmup_on_startup", True)

    with TestClient(main_module.app):
        pass

    assert called is True
