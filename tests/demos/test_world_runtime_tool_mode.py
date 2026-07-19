"""``WorldRuntime`` の ``tool_mode`` 設定切替の挙動テスト (B-4)。

検証:
- 既定 (``default``) では TODO 系を含む従来構成
- ``pure_spot_graph`` では TODO 系を除外、spot_graph_* + speech のみ
- speech 系 (say / whisper) はどちらの mode でも残る
- 不正値は ValueError で fail-fast
- 明示引数 ``include_todo_tools`` は設定より優先
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "relay_puzzle_demo.json"
)


def _tool_names(runtime) -> set[str]:
    return {d.name for d in runtime.get_tool_definitions()}


class TestWorldRuntimeToolMode:
    """``tool_mode`` 設定による get_tool_definitions の切替挙動。"""

    def test_default_mode_includes_todo_tools(self) -> None:
        """既定なら TODO 系を含む従来構成。"""
        rt = create_world_runtime(_SCENARIO_PATH)
        names = _tool_names(rt)
        assert "memo_add" in names
        assert "memo_list" in names
        assert "memo_done" in names

    def test_default_mode_explicit_config_includes_todo_tools(self) -> None:
        """``tool_mode=default`` は TODO 含む構成と同じ挙動。"""
        rt = create_world_runtime(
            _SCENARIO_PATH,
            config=ResolvedLlmRuntimeConfig.for_tests(tool_mode="default"),
        )
        assert "memo_add" in _tool_names(rt)

    def test_pure_spot_graph_mode_excludes_todo_tools(self) -> None:
        """``tool_mode=pure_spot_graph`` で TODO 系が除外される。"""
        rt = create_world_runtime(
            _SCENARIO_PATH,
            config=ResolvedLlmRuntimeConfig.for_tests(tool_mode="pure_spot_graph"),
        )
        names = _tool_names(rt)
        assert "memo_add" not in names
        assert "memo_list" not in names
        assert "memo_done" not in names

    def test_pure_spot_graph_mode_keeps_speech_tools(self) -> None:
        """speech 系 (say / whisper) は pure_spot_graph でも残る。

        エージェント間コミュニケーション観察のため speech は意図的に残す。
        """
        rt = create_world_runtime(
            _SCENARIO_PATH,
            config=ResolvedLlmRuntimeConfig.for_tests(tool_mode="pure_spot_graph"),
        )
        names = _tool_names(rt)
        # Issue #264: SAY/WHISPER を統合、PR-DD (Y_after_pr639_640 後続) で
        # speech_speak → speak にリネーム。
        assert "speak" in names

    def test_pure_spot_graph_mode_keeps_core_spot_tools(self) -> None:
        """中核の spot_graph_* (explore / travel_to / interact / wait) は残る。"""
        rt = create_world_runtime(
            _SCENARIO_PATH,
            config=ResolvedLlmRuntimeConfig.for_tests(tool_mode="pure_spot_graph"),
        )
        names = _tool_names(rt)
        for required in (
            "explore",
            "travel_to",
            "interact",
            "wait",
            "listen",
        ):
            assert required in names, f"{required} should be present in pure mode"

    def test_unknown_mode_fails_fast(self) -> None:
        """未知の値は起動時に落ちる。実験条件の typo を silent fallback しない。"""
        with pytest.raises(ValueError, match="tool_mode"):
            create_world_runtime(
                _SCENARIO_PATH,
                config=ResolvedLlmRuntimeConfig.for_tests(
                    tool_mode="unsupported_mode_value"
                ),
            )

    def test_explicit_argument_overrides_config(self) -> None:
        """factory の明示引数 ``include_todo_tools=False`` は設定より優先。"""
        rt = create_world_runtime(
            _SCENARIO_PATH,
            include_todo_tools=False,
            config=ResolvedLlmRuntimeConfig.for_tests(tool_mode="default"),
        )
        assert "memo_add" not in _tool_names(rt)

    def test_explicit_argument_true_keeps_todo_even_when_config_pure(self) -> None:
        """明示引数 ``include_todo_tools=True`` は pure_spot_graph 設定より優先。"""
        rt = create_world_runtime(
            _SCENARIO_PATH,
            include_todo_tools=True,
            config=ResolvedLlmRuntimeConfig.for_tests(tool_mode="pure_spot_graph"),
        )
        assert "memo_add" in _tool_names(rt)
