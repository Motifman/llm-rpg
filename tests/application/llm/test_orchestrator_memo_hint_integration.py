"""LlmAgentOrchestrator が memo_completion_hint_service を呼ぶか確認 (Phase 1c)。

ツール実行成功時に hint service.augment_result_summary が呼ばれ、
hint テキストが action_result_store の result_summary に反映されることを
end-to-end で検証する。
"""

from typing import Any, Dict, List, Optional

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IPromptBuilder,
    IToolArgumentResolver,
)
from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.agent_orchestrator import (
    LlmAgentOrchestrator,
)
from ai_rpg_world.application.llm.services.in_memory_memo_store import (
    InMemoryMemoStore,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubPromptBuilder(IPromptBuilder):
    def build(self, player_id: PlayerId, action_instruction: Optional[str] = None) -> Dict[str, Any]:
        return {"messages": [], "tools": [], "tool_choice": "required"}


class _StubLlmClient(ILLMClient):
    def __init__(self, name: str, arguments: Dict[str, Any]) -> None:
        self._name = name
        self._arguments = arguments

    def invoke(
        self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]], tool_choice: str = "required"
    ) -> Optional[Dict[str, Any]]:
        import json

        return {"name": self._name, "arguments": json.dumps(self._arguments)}


class _StubArgumentResolver(IToolArgumentResolver):
    def resolve(self, tool_name, arguments, runtime_context):
        return arguments


def _build_orch(
    *, memo_store: InMemoryMemoStore, tool_name: str, success_message: str
) -> tuple[LlmAgentOrchestrator, DefaultActionResultStore]:
    action_store = DefaultActionResultStore(max_entries_per_player=10)
    handler_map = {
        tool_name: lambda pid, args: LlmCommandResultDto(
            success=True, message=success_message
        )
    }
    mapper = ToolCommandMapper(handler_map=handler_map)
    hint_service = MemoCompletionHintService(
        memo_store=memo_store, similarity_threshold=0.3
    )
    # 非 memo ツールには subjective_action fields が必須なので含める
    args = {"content": "金庫室で扉固定スイッチを押す"}
    if not tool_name.startswith("memo_") and not tool_name.startswith("todo_"):
        args.update(
            {
                "inner_thought": "押そう",
                "intention": "扉を固定する",
                "expected_result": "扉が固定される",
                "attention": "スイッチ",
                "emotion_hint": "determination",
            }
        )
    orch = LlmAgentOrchestrator(
        prompt_builder=_StubPromptBuilder(),
        llm_client=_StubLlmClient(tool_name, args),
        tool_command_mapper=mapper,
        action_result_store=action_store,
        tool_argument_resolver=_StubArgumentResolver(),
        memo_completion_hint_service=hint_service,
    )
    return orch, action_store


class TestOrchestratorMemoHintIntegration:
    """LlmAgentOrchestrator と MemoCompletionHintService の統合挙動。"""

    def test_memo_と類似する成功結果に_hint_が_append_される(self) -> None:
        """非 memo ツール成功時に類似 memo があれば result_summary に hint が付く。"""
        player_id = PlayerId(1)
        memo_store = InMemoryMemoStore()
        memo_store.add(player_id, "金庫室で扉固定スイッチを押す")
        orch, action_store = _build_orch(
            memo_store=memo_store,
            tool_name="custom_tool",
            success_message="金庫室で扉固定スイッチを押しました",
        )
        orch.run_turn(player_id)
        recent = action_store.get_recent(player_id, 1)
        assert len(recent) == 1
        assert "[hint]" in recent[0].result_summary
        assert "memo_done" in recent[0].result_summary

    def test_memo_ツール自身の実行時は_hint_を出さない(self) -> None:
        """memo_add / memo_list / memo_done 実行直後に hint を出さない (自己参照防止)。"""
        player_id = PlayerId(1)
        memo_store = InMemoryMemoStore()
        memo_store.add(player_id, "金庫室で扉固定スイッチを押す")
        orch, action_store = _build_orch(
            memo_store=memo_store,
            tool_name="memo_add",
            success_message="金庫室で扉固定スイッチを押す",
        )
        orch.run_turn(player_id)
        recent = action_store.get_recent(player_id, 1)
        assert "[hint]" not in recent[0].result_summary

    def test_hint_service_未注入なら無加工で記録される(self) -> None:
        """memo_completion_hint_service が None なら hint なし。"""
        player_id = PlayerId(1)
        action_store = DefaultActionResultStore(max_entries_per_player=10)
        handler_map = {
            "custom_tool": lambda pid, args: LlmCommandResultDto(
                success=True, message="押しました"
            )
        }
        mapper = ToolCommandMapper(handler_map=handler_map)
        orch = LlmAgentOrchestrator(
            prompt_builder=_StubPromptBuilder(),
            llm_client=_StubLlmClient(
                "custom_tool",
                {
                    "inner_thought": "x",
                    "intention": "x",
                    "expected_result": "x",
                    "attention": "x",
                    "emotion_hint": "neutral",
                },
            ),
            tool_command_mapper=mapper,
            action_result_store=action_store,
            tool_argument_resolver=_StubArgumentResolver(),
        )
        orch.run_turn(player_id)
        recent = action_store.get_recent(player_id, 1)
        assert "[hint]" not in recent[0].result_summary
