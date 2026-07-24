"""Shared pytest fixtures.

The whole suite is written against the "open on loopback" default
(``ADMIN_PASSWORD`` unset), so the admin session gate in ``app.main`` is a
no-op and endpoint tests can hit ``/documents``, ``/ingest``, ``/`` directly.

But ``Settings`` reads the developer's real ``.env`` (``settings.py`` sets
``env_file=".env"``), and the deployment guide tells operators to set
``ADMIN_PASSWORD``. On such a machine every gated request would 401 and ~7
otherwise-correct tests fail — the suite would be red purely because of local
config. The autouse fixture below pins ``admin_password`` to empty for every
test so results never depend on what happens to be in ``.env``.

Tests that specifically exercise the gate (``tests/test_auth.py``) set their
own password via ``monkeypatch`` in the test body; because that runs after this
fixture, it wins for those tests.
"""

from __future__ import annotations

import pytest

from app.config.settings import settings


@pytest.fixture(autouse=True)
def _neutralize_admin_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable the admin password gate by default (see module docstring)."""
    monkeypatch.setattr(settings, "admin_password", "")


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
