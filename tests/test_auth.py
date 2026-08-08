"""Admin session gate: middleware + login/logout endpoints (app/auth.py).

Uses FastAPI's TestClient against the real app, with warmup disabled (no
Ollama/Qdrant/model loads). The accounts DB is isolated per-test by the
autouse fixture in conftest.py; tests that need the gate ENABLED provision
their own account(s) into that same per-test DB via ``accounts.create_account``.
"""

from __future__ import annotations

import app.auth as auth_module
import app.main as main_module
from app import accounts
from app.config.settings import settings


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "warmup_on_startup", False)
    return TestClient(main_module.app)


def test_gate_disabled_when_no_account_provisioned(monkeypatch) -> None:
    client = _client(monkeypatch)
    with client:
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 200


def test_protected_path_redirects_html_request_without_session(monkeypatch) -> None:
    # "/admin/" is the gated console; "/" is the public landing page (see
    # test_root_is_public_landing_page below) — REDESIGN_PROMPT.md §6/§8.
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.get(
            "/admin/", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"].startswith("/login")


def test_root_is_public_landing_page(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.get("/", headers={"accept": "text/html"}, follow_redirects=False)
        assert resp.status_code == 200


def test_protected_path_returns_401_json_for_api_request_without_session(
    monkeypatch,
) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.get("/documents", headers={"accept": "application/json"})
        assert resp.status_code == 401


def test_public_paths_bypass_gate(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        assert client.get("/health").status_code in (200, 503)  # reachable either way
        assert client.get("/login").status_code == 200


def test_email_outside_domain_is_rejected(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.post(
            "/login", data={"email": "admin@gmail.com", "password": "s3cret"}
        )
        assert resp.status_code == 401
        assert "bv_admin_session" not in resp.cookies


def test_wrong_password_rejected(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.post(
            "/login", data={"email": "admin@baoviet.com", "password": "nope"}
        )
        assert resp.status_code == 401
        assert "bv_admin_session" not in resp.cookies


def test_correct_password_grants_session_cookie_access(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.post(
            "/login", data={"email": "admin@baoviet.com", "password": "s3cret"}
        )
        assert resp.status_code == 200
        assert "bv_admin_session" in client.cookies

        resp2 = client.get("/admin/", follow_redirects=False)
        assert resp2.status_code == 200

        me = client.get("/me").json()
        assert me == {"email": "admin@baoviet.com", "role": "admin"}


def test_logout_clears_session(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "admin@baoviet.com", "password": "s3cret"})
        assert "bv_admin_session" in client.cookies

        client.post("/logout")
        resp = client.get(
            "/admin/", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert resp.status_code == 303


def test_employee_role_gets_403_on_admin_only_mutation(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        resp = client.delete("/documents/whatever")
        assert resp.status_code == 403


def test_admin_role_is_not_blocked_by_require_admin(monkeypatch) -> None:
    from app.ingestion import indexer

    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    monkeypatch.setattr(indexer, "count_document_points", lambda doc_id: 0)
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "admin@baoviet.com", "password": "s3cret"})
        resp = client.delete("/documents/whatever")
        # require_admin lets it through; a 404 here means it reached the real
        # handler (no matching doc), not a 401/403 from the auth layer.
        assert resp.status_code == 404


def test_employee_role_gets_403_on_admin_only_reads(monkeypatch) -> None:
    """GET /documents and GET /metrics/summary are admin-console data, not
    something /chat's employee accounts need (citations resolve via the
    separately-public /documents/{id}/view and /file routes instead)."""
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        assert client.get("/documents").status_code == 403
        assert client.get("/metrics/summary").status_code == 403


def test_employee_hitting_admin_page_is_redirected_to_chat(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        resp = client.get(
            "/admin/", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/chat/"


def test_employee_hitting_admin_api_gets_403_json(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        resp = client.get(
            "/admin/some-asset.js", headers={"accept": "application/json"}
        )
        assert resp.status_code == 403


def test_admin_hitting_admin_page_is_not_redirected(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "admin@baoviet.com", "password": "s3cret"})
        resp = client.get(
            "/admin/", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert resp.status_code == 200


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
    monkeypatch.setattr(settings, "api_shared_secret", "s3cr3t")
    with TestClient(main_module.app) as client:
        resp = client.get("/v1/models")
        assert resp.status_code == 401

        resp2 = client.get("/v1/models", headers={"authorization": "Bearer s3cr3t"})
        assert resp2.status_code == 200


def test_v1_route_stays_public_when_shared_secret_unset(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(settings, "warmup_on_startup", False)
    monkeypatch.setattr(settings, "api_shared_secret", "")
    with TestClient(main_module.app) as client:
        assert client.get("/v1/models").status_code == 200


def test_v1_route_accepts_account_session_even_with_shared_secret_set(
    monkeypatch,
) -> None:
    """The fix that matters once Open WebUI (the sole server-to-server caller
    of API_SHARED_SECRET) is retired: /chat's browser fetch calls /v1 with the
    account session cookie, never the bearer token — so a session must be
    enough on its own, or turning on API_SHARED_SECRET would break /chat."""
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    monkeypatch.setattr(settings, "api_shared_secret", "topsecret")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        resp = client.get("/v1/models")  # no Authorization header at all
        assert resp.status_code == 200


def test_v1_route_still_rejects_sessionless_request_with_shared_secret_set(
    monkeypatch,
) -> None:
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    monkeypatch.setattr(settings, "api_shared_secret", "topsecret")
    client = _client(monkeypatch)
    with client:
        resp = client.get("/v1/models")  # no cookie, no bearer token
        assert resp.status_code == 401
