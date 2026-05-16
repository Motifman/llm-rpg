"""create_game_app が GAME_SERVER_LOGGING_INFO_ALL で logging を構成する動作のテスト。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _scenarios_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "scenarios"


class TestCreateGameAppVerboseLoggingEnv:
    """GAME_SERVER_LOGGING_INFO_ALL と logging.basicConfig。"""

    def test_truthy_calls_basic_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """1/true/on 等では basicConfig が呼ばれる。"""
        monkeypatch.setenv("GAME_SERVER_LOGGING_INFO_ALL", "1")
        import ai_rpg_world.presentation.spot_graph_game.app as app_mod

        with patch.object(app_mod.logging, "basicConfig") as mocked:
            app_mod.create_game_app(scenarios_dir=_scenarios_dir())
        mocked.assert_called_once()

    def test_unset_does_not_call_basic_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """環境変数なしでは basicConfig を呼ばない。"""
        monkeypatch.delenv("GAME_SERVER_LOGGING_INFO_ALL", raising=False)
        import ai_rpg_world.presentation.spot_graph_game.app as app_mod

        with patch.object(app_mod.logging, "basicConfig") as mocked:
            app_mod.create_game_app(scenarios_dir=_scenarios_dir())
        mocked.assert_not_called()
