"""/chat support endpoints that aren't part of /v1 (app/api/chat_ui.py)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.main as main_module
from app import accounts
from app.config.settings import settings


def _client(monkeypatch):
    monkeypatch.setattr(settings, "warmup_on_startup", False)
    return TestClient(main_module.app)


def test_feedback_requires_a_session(monkeypatch) -> None:
    # The gate is a no-op until any account is provisioned (fresh-install
    # convention, see test_auth.py) — provision one but don't log in, so
    # this actually exercises "session required", not "gate disabled".
    accounts.create_account("admin@baoviet.com", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        resp = client.post(
            "/feedback",
            json={"completion_id": "chatcmpl-abc"},
            headers={"accept": "application/json"},
        )
        assert resp.status_code == 401


def test_employee_can_submit_feedback(monkeypatch, tmp_path) -> None:
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(settings, "feedback_log_enabled", True)
    monkeypatch.setattr(settings, "feedback_log_path", path)
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        resp = client.post(
            "/feedback", json={"completion_id": "chatcmpl-abc", "reason": "khong_dung"}
        )
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["completion_id"] == "chatcmpl-abc"
    assert record["reason"] == "khong_dung"


def test_feedback_reason_is_optional(monkeypatch, tmp_path) -> None:
    path = tmp_path / "feedback.jsonl"
    monkeypatch.setattr(settings, "feedback_log_enabled", True)
    monkeypatch.setattr(settings, "feedback_log_path", path)
    accounts.create_account("user@baoviet.com", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com", "password": "s3cret"})
        resp = client.post("/feedback", json={"completion_id": "chatcmpl-abc"})
        assert resp.status_code == 200
