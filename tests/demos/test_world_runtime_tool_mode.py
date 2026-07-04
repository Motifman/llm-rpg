"""``WorldRuntime`` の ``LLM_TOOL_MODE`` env 切替の挙動テスト (B-4)。

検証:
- 既定 (env 未設定 / ``default``) では TODO 系を含む従来構成
- ``pure_spot_graph`` では TODO 系を除外、spot_graph_* + speech のみ
- speech 系 (say / whisper) はどちらの mode でも残る
- 不正値は warning ログ + 既定 (TODO 含む) にフォールバック
- 明示引数 ``include_todo_tools`` は env より優先
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "relay_puzzle_demo.json"
)


def _tool_names(runtime) -> set[str]:
    return {d.name for d in runtime.get_tool_definitions()}


class TestWorldRuntimeToolMode:
    """``LLM_TOOL_MODE`` env による get_tool_definitions の切替挙動。"""

    def test_default_mode_includes_todo_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """env 未設定なら TODO 系を含む従来構成。"""
        monkeypatch.delenv("LLM_TOOL_MODE", raising=False)
        rt = create_world_runtime(_SCENARIO_PATH)
        names = _tool_names(rt)
        assert "memo_add" in names
        assert "memo_list" in names
        assert "memo_done" in names

    def test_default_mode_explicit_env_includes_todo_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_TOOL_MODE=default は TODO 含む構成と同じ挙動。"""
        monkeypatch.setenv("LLM_TOOL_MODE", "default")
        rt = create_world_runtime(_SCENARIO_PATH)
        assert "memo_add" in _tool_names(rt)

    def test_pure_spot_graph_mode_excludes_todo_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_TOOL_MODE=pure_spot_graph で TODO 系が除外される。"""
        monkeypatch.setenv("LLM_TOOL_MODE", "pure_spot_graph")
        rt = create_world_runtime(_SCENARIO_PATH)
        names = _tool_names(rt)
        assert "memo_add" not in names
        assert "memo_list" not in names
        assert "memo_done" not in names

    def test_pure_spot_graph_mode_keeps_speech_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """speech 系 (say / whisper) は pure_spot_graph でも残る。

        エージェント間コミュニケーション観察のため speech は意図的に残す。
        """
        monkeypatch.setenv("LLM_TOOL_MODE", "pure_spot_graph")
        rt = create_world_runtime(_SCENARIO_PATH)
        names = _tool_names(rt)
        # Issue #264: SAY/WHISPER を統合、PR-DD (Y_after_pr639_640 後続) で
        # speech_speak → speak にリネーム。
        assert "speak" in names

    def test_pure_spot_graph_mode_keeps_core_spot_tools(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """中核の spot_graph_* (explore / travel_to / interact / wait) は残る。"""
        monkeypatch.setenv("LLM_TOOL_MODE", "pure_spot_graph")
        rt = create_world_runtime(_SCENARIO_PATH)
        names = _tool_names(rt)
        for required in (
            "spot_graph_explore",
            "spot_graph_travel_to",
            "spot_graph_interact",
            "spot_graph_wait",
            "spot_graph_listen",
        ):
            assert required in names, f"{required} should be present in pure mode"

    def test_unknown_mode_falls_back_with_warning(
        self,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """未知の値は warning ログ + 既定 (TODO 含む) にフォールバック。"""
        monkeypatch.setenv("LLM_TOOL_MODE", "unsupported_mode_value")
        with caplog.at_level(
            logging.WARNING, logger="demos.world_runtime.world_runtime"
        ):
            rt = create_world_runtime(_SCENARIO_PATH)
        # TODO は含まれる (fallback)
        assert "memo_add" in _tool_names(rt)
        # warning が記録される
        assert any("Unknown LLM_TOOL_MODE" in r.message for r in caplog.records)

    def test_explicit_argument_overrides_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """factory の明示引数 ``include_todo_tools=False`` は env より優先。"""
        monkeypatch.setenv("LLM_TOOL_MODE", "default")
        rt = create_world_runtime(
            _SCENARIO_PATH, include_todo_tools=False
        )
        assert "memo_add" not in _tool_names(rt)

    def test_explicit_argument_true_keeps_todo_even_when_env_pure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """明示引数 ``include_todo_tools=True`` は env=pure_spot_graph より優先。"""
        monkeypatch.setenv("LLM_TOOL_MODE", "pure_spot_graph")
        rt = create_world_runtime(
            _SCENARIO_PATH, include_todo_tools=True
        )
        assert "memo_add" in _tool_names(rt)
