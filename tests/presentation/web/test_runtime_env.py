"""Tests for env-driven web runtime bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI

from ai_rpg_world.presentation.web.demo_seed import seed_demo_world_database
from ai_rpg_world.presentation.web.runtime import create_sqlite_web_app_from_env


def test_create_sqlite_web_app_from_env_uses_database_and_manual_player_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "env-runtime.db"
    seed_demo_world_database(database)
    monkeypatch.setenv("AI_RPG_WORLD_GAME_DB", str(database))
    monkeypatch.setenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "1,2")
    monkeypatch.setenv(
        "AI_RPG_WORLD_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )

    app = create_sqlite_web_app_from_env()

    assert isinstance(app, FastAPI)
    runtime = app.state.sqlite_web_runtime
    assert runtime.config.database_path == database
    assert runtime.config.manual_player_ids == (1, 2)
    assert runtime.config.cors_allowed_origins == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    runtime.close()


def test_create_sqlite_web_app_from_env_allows_empty_manual_player_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "env-runtime-empty.db"
    seed_demo_world_database(database)
    monkeypatch.setenv("AI_RPG_WORLD_GAME_DB", str(database))
    monkeypatch.setenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "")

    app = create_sqlite_web_app_from_env()

    runtime = app.state.sqlite_web_runtime
    assert runtime.config.manual_player_ids == ()
    assert runtime.config.cors_allowed_origins == (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    runtime.close()


def test_create_sqlite_web_app_from_env_rejects_invalid_manual_player_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    database = tmp_path / "env-runtime-invalid.db"
    seed_demo_world_database(database)
    monkeypatch.setenv("AI_RPG_WORLD_GAME_DB", str(database))
    monkeypatch.setenv("AI_RPG_WORLD_MANUAL_PLAYER_IDS", "1,hero")

    with pytest.raises(ValueError):
        create_sqlite_web_app_from_env()
