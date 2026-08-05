"""Admin session gate: middleware + login/logout endpoints (app/auth.py).

Uses FastAPI's TestClient against the real app, with warmup disabled (no
Ollama/Qdrant/model loads) and a test admin password injected via monkeypatch.
"""

from __future__ import annotations

import app.auth as auth_module
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


# ---- SEC1 (2026-08-05 audit): /v1/* shared-secret gate ----
# /v1 bypasses the admin-session cookie entirely (Open WebUI calls it
# server-to-server), so under shipped defaults it was reachable, unauthenticated,
# from anywhere the API host is reachable -- including the whole LAN once an
# operator follows README's own guidance to set API_HOST=0.0.0.0. These pin
# check_shared_secret() and the /v1 gate in the middleware itself.


def test_shared_secret_empty_means_unchanged_default_behavior(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_shared_secret", "")
    assert auth_module.check_shared_secret(None) is True
    assert auth_module.check_shared_secret("Bearer anything") is True


def test_shared_secret_rejects_missing_or_wrong_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_shared_secret", "s3cr3t")
    assert auth_module.check_shared_secret(None) is False
    assert auth_module.check_shared_secret("Bearer wrong") is False
    assert auth_module.check_shared_secret("s3cr3t") is False  # missing "Bearer "


def test_shared_secret_accepts_matching_bearer_header(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_shared_secret", "s3cr3t")
    assert auth_module.check_shared_secret("Bearer s3cr3t") is True


def test_v1_route_rejects_request_without_shared_secret_when_configured(
    monkeypatch,
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "warmup_on_startup", False)
    monkeypatch.setattr(settings, "admin_password", "")  # admin gate irrelevant here
    monkeypatch.setattr(settings, "api_shared_secret", "s3cr3t")
    with TestClient(main_module.app) as client:
        resp = client.get("/v1/models")
        assert resp.status_code == 401

        resp2 = client.get(
            "/v1/models", headers={"authorization": "Bearer s3cr3t"}
        )
        assert resp2.status_code == 200


def test_v1_route_stays_public_when_shared_secret_unset(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "warmup_on_startup", False)
    monkeypatch.setattr(settings, "admin_password", "")
    monkeypatch.setattr(settings, "api_shared_secret", "")
    with TestClient(main_module.app) as client:
        assert client.get("/v1/models").status_code == 200
