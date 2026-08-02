"""spot_graph_game がブラウザ用 CORS を明示設定時だけ許可することを保証する。"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.middleware.cors import CORSMiddleware

from ai_rpg_world.presentation.spot_graph_game.app import create_game_app
from ai_rpg_world.presentation.spot_graph_game import server


def test_create_game_app_does_not_allow_cors_by_default(tmp_path: Path) -> None:
    """cors_origins を省略すると、ローカルのブラウザ開発元も既定許可しない。"""
    app = create_game_app(scenarios_dir=tmp_path)

    cors_middleware = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls is CORSMiddleware
    )

    assert cors_middleware.kwargs["allow_origins"] == []


def test_server_does_not_allow_cors_when_env_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAME_CORS_ORIGINS が未設定なら、サーバ入口は空の許可元を渡す。"""
    monkeypatch.delenv("GAME_CORS_ORIGINS", raising=False)
    captured: dict[str, Any] = {}
    expected_app = MagicMock()

    def _capture_create_game_app(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return expected_app

    monkeypatch.setattr(server, "create_game_app", _capture_create_game_app)

    assert server.create_app_from_env() is expected_app
    assert captured["cors_origins"] == []


def test_server_preserves_explicit_cors_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GAME_CORS_ORIGINS を指定すると、空白を除いた許可元だけを渡す。"""
    monkeypatch.setenv(
        "GAME_CORS_ORIGINS",
        " https://observer.example, https://admin.example ",
    )
    captured: dict[str, Any] = {}

    def _capture_create_game_app(**kwargs: Any) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(server, "create_game_app", _capture_create_game_app)

    server.create_app_from_env()

    assert captured["cors_origins"] == [
        "https://observer.example",
        "https://admin.example",
    ]
