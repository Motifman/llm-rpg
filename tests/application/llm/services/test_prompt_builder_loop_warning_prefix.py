"""DefaultPromptBuilder の loop_guard 警告 prefix の挙動。

直前ターンで同じ (tool, 引数) を選んでいた場合、instruction の前に
警告文を挟む。tool_call_loop_guard.peek_streak の戻り値で出し分けする。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
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
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
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
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _CurrentStateSource:
    def __init__(self) -> None:
        self.queries: list[GetPlayerCurrentStateQuery] = []

    def get_player_current_state(self, query: GetPlayerCurrentStateQuery) -> PlayerCurrentStateDto | None:
        self.queries.append(query)
        return None


def _make_core() -> PromptBuilderCoreServices:
    return PromptBuilderCoreServices(
        observation_buffer=MagicMock(spec=IObservationContextBuffer),
        recent_event_store=UnifiedRecentEventStore(),
        world_query_service=_CurrentStateSource(),
        player_profile_repository=MagicMock(spec=PlayerProfileRepository),
        current_state_formatter=MagicMock(spec=ICurrentStateFormatter),
        context_format_strategy=MagicMock(spec=IContextFormatStrategy),
        system_prompt_builder=MagicMock(spec=ISystemPromptBuilder),
        available_tools_provider=MagicMock(spec=IAvailableToolsProvider),
        recent_events_text_provider=lambda being_id: "",
        backstory_text_provider=lambda being_id: "",
    )


def _pid(value: int) -> PlayerId:
    return PlayerId.create(value)


class TestPromptBuilderLoopWarningPrefix:
    """直前ターンと同じ手を選ぼうとしているとき instruction 末尾に警告 prefix を載せる挙動を保証する。"""

    def test_loop_guard_uninjected_empty_string(self) -> None:
        """tool_call_loop_guard=None なら警告 prefix は出ない (= 既存挙動)。"""
        builder = DefaultPromptBuilder(_make_core(), ui_context_builder=MagicMock(spec=ILlmUiContextBuilder))
        assert builder._build_loop_warning_prefix(_pid(1)) == ""

    def test_one_empty_string(self) -> None:
        """直前と違う手なら警告は出さない (peek_streak が None を返す)。"""
        buf = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(buf, lambda: None)
        guard.record_and_check(_pid(1), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        builder = DefaultPromptBuilder(
            _make_core(), ui_context_builder=MagicMock(spec=ILlmUiContextBuilder), tool_call_loop_guard=guard
        )
        assert builder._build_loop_warning_prefix(_pid(1)) == ""

    def test_two_tool_count_prefix_included(self) -> None:
        """同じ tool + 同じ引数を 2 連続したら、prefix に tool 名と回数が乗る。"""
        buf = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(buf, lambda: None)
        pid = _pid(1)
        guard.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        guard.record_and_check(pid, TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        builder = DefaultPromptBuilder(
            _make_core(), ui_context_builder=MagicMock(spec=ILlmUiContextBuilder), tool_call_loop_guard=guard
        )
        prefix = builder._build_loop_warning_prefix(pid)
        assert TOOL_NAME_SPOT_GRAPH_TRAVEL_TO in prefix
        assert "2" in prefix
        # 「同じ手」「別の選択肢」など、行動を変えるよう促す語が含まれる
        assert "同じ" in prefix and "別" in prefix

    def test_other_player_streak(self) -> None:
        """player_id ごとに独立。別 player の streak が漏れて来ない。"""
        buf = DefaultObservationContextBuffer()
        guard = ToolCallLoopGuardService(buf, lambda: None)
        guard.record_and_check(_pid(1), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        guard.record_and_check(_pid(1), TOOL_NAME_SPOT_GRAPH_TRAVEL_TO, {"target": "X"})
        builder = DefaultPromptBuilder(
            _make_core(), ui_context_builder=MagicMock(spec=ILlmUiContextBuilder), tool_call_loop_guard=guard
        )
        # player 2 はまだ何もしていない
        assert builder._build_loop_warning_prefix(_pid(2)) == ""

    def test_guard_raises_type_error(self) -> None:
        """型違いの guard を渡したら TypeError。"""
        with pytest.raises(TypeError):
            DefaultPromptBuilder(
                _make_core(),
                ui_context_builder=MagicMock(spec=ILlmUiContextBuilder),
                tool_call_loop_guard="not a guard",
            )  # type: ignore[arg-type]


def test_prompt_builder_requires_ui_context_builder() -> None:
    """UI構築器を省略すると、存在しないタイル実装へ戻らず構築時に拒否する。"""
    with pytest.raises(TypeError, match="ui_context_builder"):
        DefaultPromptBuilder(_make_core())


@pytest.mark.parametrize("invalid_builder", [None, "invalid"])
def test_prompt_builder_rejects_invalid_ui_context_builder(invalid_builder) -> None:
    """UI構築器にNoneか別の型を渡すと、構築時にTypeErrorで拒否する。"""
    with pytest.raises(TypeError, match="ui_context_builder"):
        DefaultPromptBuilder(_make_core(), ui_context_builder=invalid_builder)


def test_prompt_builder_uses_only_current_state_source() -> None:
    """現在状態の取得だけを持つ依存先でも、未配置を示すプロンプトを構築できる。"""
    from ai_rpg_world.application.being.acting_being import ActingBeing
    from ai_rpg_world.application.llm.services.prompt_builder import MESSAGE_WHEN_PLAYER_NOT_PLACED
    from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import SpotGraphUiContextBuilder
    from ai_rpg_world.being.domain.being_id import BeingId

    core = _make_core()
    profile = core.player_profile_repository.find_by_id.return_value
    profile.name.value = "旅人"
    profile.role.value = "citizen"
    profile.race.value = "human"
    profile.element.value = "neutral"
    core.observation_buffer.drain.return_value = []
    core.context_format_strategy.format.side_effect = lambda **kwargs: kwargs["current_state_text"]
    core.system_prompt_builder.build.return_value = "世界の説明"
    builder = DefaultPromptBuilder(core, ui_context_builder=SpotGraphUiContextBuilder())

    result = builder.build(ActingBeing(_pid(1), BeingId("test-being")))

    assert core.world_query_service.queries == [GetPlayerCurrentStateQuery(player_id=1)]
    assert MESSAGE_WHEN_PLAYER_NOT_PLACED in result["messages"][1]["content"]
    core.current_state_formatter.format.assert_not_called()
