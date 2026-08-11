"""Per-account profile preferences (app/user_prefs.py)."""

from __future__ import annotations

import pytest

from app import user_prefs


def test_get_prefs_empty_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(user_prefs.settings, "data_dir", tmp_path)
    prefs = user_prefs.get_prefs("user@baoviet.com.vn")
    assert prefs.display_name is None
    assert prefs.avatar_swatch is None


def test_update_display_name_and_avatar(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(user_prefs.settings, "data_dir", tmp_path)
    user_prefs.update_prefs(
        "user@baoviet.com.vn",
        display_name="Nguyễn Văn A",
        avatar_swatch="gold",
    )
    prefs = user_prefs.get_prefs("user@baoviet.com.vn")
    assert prefs.display_name == "Nguyễn Văn A"
    assert prefs.avatar_swatch == "gold"


def test_update_rejects_empty_display_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(user_prefs.settings, "data_dir", tmp_path)
    with pytest.raises(ValueError, match="Tên hiển thị"):
        user_prefs.update_prefs("user@baoviet.com.vn", display_name="  ")


def test_update_rejects_invalid_avatar_swatch(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(user_prefs.settings, "data_dir", tmp_path)
    with pytest.raises(ValueError, match="avatar"):
        user_prefs.update_prefs("user@baoviet.com.vn", avatar_swatch="hotpink")
