"""LlmAgentOrchestrator が trace_recorder に action / action_result を自動 record するか確認 (Phase 1d 配線)。"""

from typing import Any, Dict, List, Optional

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    ILLMClient,
    IPromptBuilder,
    IToolArgumentResolver,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.agent_orchestrator import (
    LlmAgentOrchestrator,
)
from ai_rpg_world.application.llm.services.tool_command_mapper import ToolCommandMapper
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEvent, TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _StubPromptBuilder(IPromptBuilder):
    def build(self, player_id: PlayerId, action_instruction: Optional[str] = None) -> Dict[str, Any]:
        return {"messages": [], "tools": [], "tool_choice": "required"}


class _StubLlmClient(ILLMClient):
    def __init__(self, name: str, arguments: Dict[str, Any]) -> None:
        self._name = name
        self._arguments = arguments

    def invoke(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
    ) -> Optional[Dict[str, Any]]:
        import json
        return {"name": self._name, "arguments": json.dumps(self._arguments)}


class _StubArgumentResolver(IToolArgumentResolver):
    def resolve(self, tool_name, arguments, runtime_context):
        return arguments


class _CapturingRecorder(ITraceRecorder):
    """記録された TraceEvent を全部メモリに保持する recorder。"""

    def __init__(self) -> None:
        self._seq = 0
        self.events: List[TraceEvent] = []

    def record(self, kind, *, tick=None, player_id=None, **payload):
        self._seq += 1
        ev = TraceEvent(
            seq=self._seq,
            timestamp="2026-01-01T00:00:00+00:00",
            kind=str(kind),
            tick=tick,
            player_id=player_id,
            payload=dict(payload),
        )
        self.events.append(ev)
        return ev

    def close(self) -> None:
        pass


def _build_orch(*, recorder, tick_provider=lambda: 7):
    action_store = DefaultActionResultStore(max_entries_per_player=10)
    handler_map = {
        "custom_tool": lambda pid, args: LlmCommandResultDto(
            success=True, message="押しました"
        )
    }
    mapper = ToolCommandMapper(handler_map=handler_map)
    args = {
        "content": "x",
        "inner_thought": "y",
        "intention": "y",
        "expected_result": "y",
        "attention": "y",
        "emotion_hint": "neutral",
    }
    return LlmAgentOrchestrator(
        prompt_builder=_StubPromptBuilder(),
        llm_client=_StubLlmClient("custom_tool", args),
        tool_command_mapper=mapper,
        action_result_store=action_store,
        tool_argument_resolver=_StubArgumentResolver(),
        trace_recorder=recorder,
        tick_provider=tick_provider,
    )


class TestOrchestratorTraceRecording:
    """LlmAgentOrchestrator が action / action_result を trace に自動記録する挙動。"""

    def test_ツール成功時に_action_と_action_result_が_record_される(self) -> None:
        """非 memo ツール成功時に 2 件 (ACTION, ACTION_RESULT) が同 tick で記録される。"""
        rec = _CapturingRecorder()
        orch = _build_orch(recorder=rec)
        orch.run_turn(PlayerId(1))

        kinds = [e.kind for e in rec.events]
        assert TraceEventKind.ACTION in kinds
        assert TraceEventKind.ACTION_RESULT in kinds

        action_event = next(e for e in rec.events if e.kind == TraceEventKind.ACTION)
        result_event = next(e for e in rec.events if e.kind == TraceEventKind.ACTION_RESULT)
        assert action_event.player_id == 1
        assert action_event.tick == 7
        assert action_event.payload["tool"] == "custom_tool"
        assert result_event.payload["success"] is True
        assert result_event.payload["tool"] == "custom_tool"

    def test_recorder_未注入なら_NullTraceRecorder_でクラッシュしない(self) -> None:
        """trace_recorder=None でも orchestrator は動作する (黙って no-op)。"""
        action_store = DefaultActionResultStore(max_entries_per_player=10)
        handler_map = {
            "custom_tool": lambda pid, args: LlmCommandResultDto(success=True, message="ok")
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
        # クラッシュしないこと
        orch.run_turn(PlayerId(1))

    def test_tick_provider_例外時は_tick_None_として記録する(self) -> None:
        """tick_provider が例外を投げても trace 記録は継続する (tick=None)。"""
        rec = _CapturingRecorder()

        def bad_provider() -> int:
            raise RuntimeError("boom")

        orch = _build_orch(recorder=rec, tick_provider=bad_provider)
        orch.run_turn(PlayerId(1))
        action_event = next(e for e in rec.events if e.kind == TraceEventKind.ACTION)
        assert action_event.tick is None
