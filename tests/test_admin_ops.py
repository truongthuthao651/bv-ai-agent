"""Admin config, logs, and eval-run endpoints."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

import app.main as main_module
from app import accounts
from app.config.settings import settings


def _client(monkeypatch):
    monkeypatch.setattr(settings, "warmup_on_startup", False)
    return TestClient(main_module.app)


def test_admin_config_requires_admin(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com.vn", "s3cret", "employee")
    accounts.create_account("admin@baoviet.com.vn", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post(
            "/login", data={"email": "user@baoviet.com.vn", "password": "s3cret"}
        )
        assert client.get("/admin/config").status_code == 403
        client.post("/logout")
        client.post(
            "/login", data={"email": "admin@baoviet.com.vn", "password": "s3cret"}
        )
        resp = client.get("/admin/config")
        assert resp.status_code == 200
        data = resp.json()
        assert "chat_model" in data
        assert "session_secret_key" not in data


def test_admin_feedback_log(monkeypatch, tmp_path) -> None:
    log_path = tmp_path / "feedback.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "ts": "2026-08-09T12:00:00+00:00",
                "completion_id": "chatcmpl-1",
                "reason": "Quyền lợi được trả lời chưa đúng điều khoản.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "feedback_log_enabled", True)
    monkeypatch.setattr(settings, "feedback_log_path", str(log_path))
    accounts.create_account("admin@baoviet.com.vn", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post(
            "/login", data={"email": "admin@baoviet.com.vn", "password": "s3cret"}
        )
        resp = client.get("/admin/logs/feedback")
        assert resp.status_code == 200
        assert resp.json()["records"][0]["completion_id"] == "chatcmpl-1"
        assert (
            resp.json()["records"][0]["reason"]
            == "Quyền lợi được trả lời chưa đúng điều khoản."
        )


def test_admin_eval_runs_empty_when_no_results(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com.vn", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post(
            "/login", data={"email": "admin@baoviet.com.vn", "password": "s3cret"}
        )
        resp = client.get("/admin/eval-runs")
        assert resp.status_code == 200
        assert "runs" in resp.json()
