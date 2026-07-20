"""Admin session gate: middleware + login/logout endpoints (app/auth.py).

Uses FastAPI's TestClient against the real app, with warmup disabled (no
Ollama/Qdrant/model loads) and a test admin password injected via monkeypatch.
"""

from __future__ import annotations

import app.main as main_module
from app.config.settings import settings


def _client(monkeypatch, *, password: str = ""):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "warmup_on_startup", False)
    monkeypatch.setattr(settings, "admin_password", password)
    return TestClient(main_module.app)


def test_gate_disabled_when_no_password_set(monkeypatch) -> None:
    client = _client(monkeypatch, password="")
    with client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200


def test_protected_path_redirects_html_request_without_session(monkeypatch) -> None:
    client = _client(monkeypatch, password="s3cret")
    with client:
        resp = client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")


def test_protected_path_returns_401_json_for_api_request_without_session(
    monkeypatch,
) -> None:
    client = _client(monkeypatch, password="s3cret")
    with client:
        resp = client.get("/documents", headers={"accept": "application/json"})
        assert resp.status_code == 401


def test_public_paths_bypass_gate(monkeypatch) -> None:
    client = _client(monkeypatch, password="s3cret")
    with client:
        assert client.get("/health").status_code in (200, 503)  # reachable either way
        assert client.get("/login").status_code == 200


def test_wrong_password_rejected(monkeypatch) -> None:
    client = _client(monkeypatch, password="s3cret")
    with client:
        resp = client.post("/login", data={"password": "nope"})
        assert resp.status_code == 401
        assert "bv_admin_session" not in resp.cookies


def test_correct_password_grants_session_cookie_access(monkeypatch) -> None:
    client = _client(monkeypatch, password="s3cret")
    with client:
        resp = client.post("/login", data={"password": "s3cret"})
        assert resp.status_code == 200
        assert "bv_admin_session" in client.cookies

        resp2 = client.get("/", follow_redirects=False)
        assert resp2.status_code == 200


def test_logout_clears_session(monkeypatch) -> None:
    client = _client(monkeypatch, password="s3cret")
    with client:
        client.post("/login", data={"password": "s3cret"})
        assert "bv_admin_session" in client.cookies

        client.post("/logout")
        resp = client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
        assert resp.status_code == 303
