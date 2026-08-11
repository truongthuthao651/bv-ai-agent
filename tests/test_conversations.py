"""Per-user conversation API — privacy: no cross-account access, no admin list."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.main as main_module
from app import accounts
from app.config.settings import settings


def _client(monkeypatch):
    monkeypatch.setattr(settings, "warmup_on_startup", False)
    return TestClient(main_module.app)


def test_conversations_require_session(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com.vn", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        assert client.get("/conversations").status_code == 401


def test_user_sees_only_own_conversations(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com.vn", "s3cret", "employee")
    accounts.create_account("other@baoviet.com.vn", "s3cret", "employee")
    accounts.create_account("admin@baoviet.com.vn", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post(
            "/login", data={"email": "user@baoviet.com.vn", "password": "s3cret"}
        )
        sync = client.post(
            "/conversations/sync",
            json={
                "conversations": [
                    {
                        "id": "conv-a",
                        "title": "Private thread",
                        "messages": [{"role": "user", "text": "hello"}],
                        "updatedAt": 1_700_000_000_000,
                    }
                ],
                "activeId": "conv-a",
            },
        )
        assert sync.status_code == 200

        client.post("/logout")
        client.post(
            "/login", data={"email": "other@baoviet.com.vn", "password": "s3cret"}
        )
        other = client.get("/conversations").json()
        assert other["conversations"] == []

        client.post("/logout")
        client.post(
            "/login", data={"email": "admin@baoviet.com.vn", "password": "s3cret"}
        )
        admin_list = client.get("/conversations").json()
        assert admin_list["conversations"] == []


def test_admin_has_no_conversation_admin_route(monkeypatch) -> None:
    accounts.create_account("admin@baoviet.com.vn", "s3cret", "admin")
    client = _client(monkeypatch)
    with client:
        client.post(
            "/login", data={"email": "admin@baoviet.com.vn", "password": "s3cret"}
        )
        assert client.get("/admin/conversations").status_code == 404


def test_delete_conversation(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com.vn", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post(
            "/login", data={"email": "user@baoviet.com.vn", "password": "s3cret"}
        )
        client.post(
            "/conversations/sync",
            json={
                "conversations": [
                    {
                        "id": "conv-x",
                        "title": "To delete",
                        "messages": [{"role": "user", "text": "x"}],
                        "updatedAt": 1,
                    }
                ],
                "activeId": "conv-x",
            },
        )
        assert client.delete("/conversations/conv-x").status_code == 200
        assert client.get("/conversations").json()["conversations"] == []


def test_feedback_status_is_preserved_in_conversation(monkeypatch) -> None:
    accounts.create_account("user@baoviet.com.vn", "s3cret", "employee")
    client = _client(monkeypatch)
    with client:
        client.post("/login", data={"email": "user@baoviet.com.vn", "password": "s3cret"})
        client.post(
            "/conversations/sync",
            json={
                "conversations": [
                    {
                        "id": "conv-feedback",
                        "title": "Feedback state",
                        "messages": [
                            {
                                "role": "assistant",
                                "text": "Answer",
                                "completionId": "chatcmpl-abc",
                                "feedbackSent": True,
                            }
                        ],
                        "updatedAt": 1_700_000_000_000,
                    }
                ],
                "activeId": "conv-feedback",
            },
        )
        message = client.get("/conversations").json()["conversations"][0]["messages"][0]
        assert message["feedbackSent"] is True
