"""LlmAgentOrchestrator のテスト（正常・例外・ツール未選択）"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import IPromptBuilder
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.agent_orchestrator import (
    LlmAgentOrchestrator,
)
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.services.tool_command_mapper import (
    ToolCommandMapper,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_NO_OP
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubPromptBuilder(IPromptBuilder):
    """テスト用: build が固定の辞書を返す IPromptBuilder 実装。"""

    def __init__(self, return_value: dict):
        self._return_value = return_value

    def build(self, player_id, action_instruction=None):
        return self._return_value


class TestLlmAgentOrchestratorRunTurn:
    """run_turn の正常・境界ケース"""

    @pytest.fixture
    def prompt_builder(self):
        """messages / tools / tool_choice を返すスタブ（IPromptBuilder 実装）"""
        return _StubPromptBuilder(return_value={
            "messages": [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "user"},
            ],
            "tools": [{"type": "function", "function": {"name": TOOL_NAME_NO_OP, "description": "", "parameters": {}}}],
            "tool_choice": "required",
        })

    @pytest.fixture
    def action_result_store(self):
        return DefaultActionResultStore(max_entries_per_player=10)

    @pytest.fixture
    def mapper(self):
        return ToolCommandMapper(movement_service=MagicMock())

    @pytest.fixture
    def orchestrator(self, prompt_builder, action_result_store, mapper):
        llm_client = StubLlmClient(tool_call_to_return={"name": TOOL_NAME_NO_OP, "arguments": {}})
        return LlmAgentOrchestrator(
            prompt_builder=prompt_builder,
            llm_client=llm_client,
            tool_command_mapper=mapper,
            action_result_store=action_result_store,
        )

    def test_run_turn_invokes_prompt_builder_and_llm(self, orchestrator, prompt_builder):
        """run_turn が prompt_builder.build を 1 回呼ぶ"""
        player_id = PlayerId(1)
        orchestrator.run_turn(player_id)
        assert prompt_builder._return_value["messages"]  # build が使われた結果 request が組立てられている

    def test_run_turn_appends_to_action_result_store(self, orchestrator, action_result_store):
        """run_turn 後に store に 1 件 append される"""
        player_id = PlayerId(1)
        orchestrator.run_turn(player_id)
        recent = action_result_store.get_recent(player_id, 5)
        assert len(recent) == 1
        assert "world_no_op" in recent[0].action_summary or "no_op" in recent[0].action_summary
        assert recent[0].result_summary

    def test_run_turn_returns_llm_command_result_dto(self, orchestrator):
        """run_turn の戻り値は LlmCommandResultDto"""
        result = orchestrator.run_turn(PlayerId(1))
        assert isinstance(result, LlmCommandResultDto)
        assert result.success is True

    def test_run_turn_when_no_tool_call_appends_no_tool_message(self, action_result_store, mapper):
        """LLM が tool_call を返さないとき「ツールが選択されませんでした」が store に記録される"""
        prompt_builder = _StubPromptBuilder(return_value={
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            "tools": [],
            "tool_choice": "required",
        })
        llm_client = StubLlmClient(tool_call_to_return=None)
        orchestrator = LlmAgentOrchestrator(
            prompt_builder=prompt_builder,
            llm_client=llm_client,
            tool_command_mapper=mapper,
            action_result_store=action_result_store,
        )
        result = orchestrator.run_turn(PlayerId(1))
        assert result.success is False
        assert "ツール" in result.message or "tool" in result.message.lower()
        recent = action_result_store.get_recent(PlayerId(1), 5)
        assert len(recent) == 1
        assert "選択されませんでした" in recent[0].action_summary or "ツール" in recent[0].action_summary

    def test_run_turn_player_id_not_player_id_raises_type_error(self, orchestrator):
        """player_id が PlayerId でないとき TypeError"""
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            orchestrator.run_turn(1)  # type: ignore[arg-type]


class TestLlmAgentOrchestratorInit:
    """コンストラクタのバリデーション"""

    def test_init_prompt_builder_not_iprompt_builder_raises_type_error(self):
        """prompt_builder が IPromptBuilder でないとき TypeError"""
        with pytest.raises(TypeError, match="prompt_builder must be IPromptBuilder"):
            LlmAgentOrchestrator(
                prompt_builder=None,  # type: ignore[arg-type]
                llm_client=StubLlmClient(),
                tool_command_mapper=ToolCommandMapper(movement_service=MagicMock()),
                action_result_store=DefaultActionResultStore(),
            )

    def test_init_llm_client_not_illm_client_raises_type_error(self):
        """llm_client が ILLMClient でないとき TypeError"""
        with pytest.raises(TypeError, match="llm_client must be ILLMClient"):
            LlmAgentOrchestrator(
                prompt_builder=_StubPromptBuilder(return_value={"messages": [], "tools": [], "tool_choice": "required"}),
                llm_client=None,  # type: ignore[arg-type]
                tool_command_mapper=ToolCommandMapper(movement_service=MagicMock()),
                action_result_store=DefaultActionResultStore(),
            )
