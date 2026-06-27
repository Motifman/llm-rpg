"""DefaultPromptBuilder の loop_guard 警告 prefix の挙動。

直前ターンで同じ (tool, 引数) を選んでいた場合、instruction の前に
警告文を挟む。tool_call_loop_guard.peek_streak の戻り値で出し分けする。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.services.prompt_builder import (
    DefaultPromptBuilder,
)
from ai_rpg_world.application.llm.services.prompt_builder_config import (
    PromptBuilderCoreServices,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _make_core() -> PromptBuilderCoreServices:
    return PromptBuilderCoreServices(
        observation_buffer=MagicMock(spec=IObservationContextBuffer),
        sliding_window_memory=MagicMock(spec=ISlidingWindowMemory),
        action_result_store=MagicMock(spec=IActionResultStore),
        world_query_service=MagicMock(spec=WorldQueryService),
        player_profile_repository=MagicMock(spec=PlayerProfileRepository),
        current_state_formatter=MagicMock(spec=ICurrentStateFormatter),
        recent_events_formatter=MagicMock(spec=IRecentEventsFormatter),
        context_format_strategy=MagicMock(spec=IContextFormatStrategy),
        system_prompt_builder=MagicMock(spec=ISystemPromptBuilder),
        available_tools_provider=MagicMock(spec=IAvailableToolsProvider),
    )


def _pid(value: int) -> PlayerId:
    return PlayerId.create(value)


class TestPromptBuilderLoopWarningPrefix:
    """直前ターンと同じ手を選ぼうとしているとき instruction 末尾に警告 prefix を載せる挙動を保証する。"""

    def test_loop_guard_未注入なら_空文字(self) -> None:
        """tool_call_loop_guard=None なら警告 prefix は出ない (= 既存挙動)。"""
        builder = DefaultPromptBuilder(_make_core())
        assert builder._build_loop_warning_prefix(_pid(1)) == ""

    def test_連続_1回目_では_空文字(self) -> None:
        """直前と違う手なら警告は出さない (peek_streak が None を返す)。"""
        buf = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(buf)
        guard.record_and_check(_pid(1), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        builder = DefaultPromptBuilder(_make_core(), tool_call_loop_guard=guard)
        assert builder._build_loop_warning_prefix(_pid(1)) == ""

    def test_連続_2回目_でtool名と回数が_prefix_に含まれる(self) -> None:
        """同じ tool + 同じ引数を 2 連続したら、prefix に tool 名と回数が乗る。"""
        buf = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(buf)
        pid = _pid(1)
        guard.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        guard.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        builder = DefaultPromptBuilder(_make_core(), tool_call_loop_guard=guard)
        prefix = builder._build_loop_warning_prefix(pid)
        assert TOOL_NAME_SPOT_GRAPH_TRAVEL_TO in prefix
        assert "2" in prefix
        # 「同じ手」「別の選択肢」など、行動を変えるよう促す語が含まれる
        assert "同じ" in prefix and "別" in prefix

    def test_他プレイヤーのstreak_は混ざらない(self) -> None:
        """player_id ごとに独立。別 player の streak が漏れて来ない。"""
        buf = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(buf)
        guard.record_and_check(_pid(1), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        guard.record_and_check(_pid(1), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        builder = DefaultPromptBuilder(_make_core(), tool_call_loop_guard=guard)
        # player 2 はまだ何もしていない
        assert builder._build_loop_warning_prefix(_pid(2)) == ""

    def test_型違いの_guard_を渡したら_TypeError(self) -> None:
        with pytest.raises(TypeError):
            DefaultPromptBuilder(_make_core(), tool_call_loop_guard="not a guard")  # type: ignore[arg-type]
