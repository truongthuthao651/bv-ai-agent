"""Shared pytest fixtures.

The whole suite is written against the "open on loopback" default (no
accounts provisioned), so the admin session gate in ``app.main`` is a no-op
and endpoint tests can hit ``/documents``, ``/ingest``, ``/`` directly.

The gate is driven by ``app.accounts.any_accounts_exist()`` against a real
SQLite file at ``settings.data_dir / "accounts.db"`` — on a dev machine that
has actually seeded demo accounts (scripts/seed_accounts.py), the unmodified
default ``data_dir`` would point at that same real file and every gated
request would 401, making the suite red purely because of local state. The
autouse fixture below points every test at an empty, per-test accounts DB so
results never depend on what accounts happen to be provisioned on disk.

Tests that specifically exercise the gate (``tests/test_auth.py``) provision
their own accounts into that same per-test DB via ``app.accounts.create_account``.
"""

from __future__ import annotations

import pytest

from app import accounts
from app.config.settings import settings


@pytest.fixture(autouse=True)
def _isolated_conversations_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point conversation storage at an empty per-test DB."""
    from app import conversations as conv_mod

    monkeypatch.setattr(conv_mod, "_db_path", lambda: tmp_path / "conversations.db")


@pytest.fixture(autouse=True)
def _isolated_accounts_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the accounts store at an empty per-test DB (see module docstring)."""
    monkeypatch.setattr(accounts, "_db_path", lambda: tmp_path / "accounts.db")


@pytest.fixture(autouse=True)
def _neutralize_query_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn off the response-time footer and timing log for the whole suite.

    The footer changes answer text and the log writes a file; neither belongs in
    unit tests that assert exact response content. Tests that specifically cover
    the timing feature re-enable ``show_response_time`` themselves.
    """
    monkeypatch.setattr(settings, "show_response_time", False)
    monkeypatch.setattr(settings, "query_timing_log_enabled", False)


@pytest.fixture(autouse=True)
def _no_implicit_index_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep product/comparison helpers from implicitly reading the live Qdrant.

    ``named_product_labels`` / ``is_multi_product_query`` load indexed titles when
    the caller passes none, so their result would otherwise depend on whether the
    embedded store happens to be readable during the test run (it is when the API
    is stopped for an eval, locked when it's running). Pinning the loaders to
    empty makes those tests hermetic — they exercise the cue-span fallback; tests
    that need real titles inject them explicitly.
    """
    from app.retrieval import comparison, product_scope

    monkeypatch.setattr(product_scope, "_load_indexed_titles", lambda: [])
    monkeypatch.setattr(comparison, "_load_indexed_docs", lambda: [])
