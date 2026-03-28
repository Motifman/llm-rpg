"""Tests for env-driven web runtime bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from ai_rpg_world.presentation.web.runtime import create_sqlite_web_app_from_env
from tests.presentation.web.test_runtime import _seed_world


def test_create_sqlite_web_app_from_env_uses_database_and_manual_player_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "env-runtime.db"
    _seed_world(database)
    monkeypatch.setenv("AI_RPG_WORLD_GAME_DB", str(database))
    monkeypatch.setenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "1,2")

    app = create_sqlite_web_app_from_env()

    assert isinstance(app, FastAPI)
    runtime = app.state.sqlite_web_runtime
    assert runtime.config.database_path == database
    assert runtime.config.manual_player_ids == (1, 2)
    runtime.close()


def test_create_sqlite_web_app_from_env_allows_empty_manual_player_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "env-runtime-empty.db"
    _seed_world(database)
    monkeypatch.setenv("AI_RPG_WORLD_GAME_DB", str(database))
    monkeypatch.setenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "")

    app = create_sqlite_web_app_from_env()

    runtime = app.state.sqlite_web_runtime
    assert runtime.config.manual_player_ids == ()
    runtime.close()


def test_create_sqlite_web_app_from_env_rejects_invalid_manual_player_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "env-runtime-invalid.db"
    _seed_world(database)
    monkeypatch.setenv("AI_RPG_WORLD_GAME_DB", str(database))
    monkeypatch.setenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "1,hero")

    with pytest.raises(ValueError):
        create_sqlite_web_app_from_env()
