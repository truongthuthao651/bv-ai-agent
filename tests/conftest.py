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
