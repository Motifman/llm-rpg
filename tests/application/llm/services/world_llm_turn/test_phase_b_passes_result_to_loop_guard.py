"""phase_b が、行動の結果の文をループ警告の入口へ渡す。

繰り返しの理由の見立て (#1411) は、直近の行動の結果を材料にする。入口へ渡さないと、
見立ては行動の名前だけで理由を当てることになる。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.world_llm_turn import phase_b
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def test_the_result_message_reaches_record_and_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """失敗した行動の message が、record_and_check の result_summary に届く。"""
    monkeypatch.setattr(
        phase_b,
        "execute_tool",
        MagicMock(
            return_value=LlmCommandResultDto(
                success=False,
                message="麦束がありません。",
                error_code="INTERACTION_PRECONDITION_FAILED",
            )
        ),
    )
    monkeypatch.setattr(phase_b, "maybe_interrupt_busy", MagicMock(return_value=(False, None)))
    monkeypatch.setattr(phase_b, "record_prompt_dataset_turn_result", MagicMock())
    wiring = MagicMock()
    wiring.runtime.trace_recorder = None
    wiring.memo_completion_hint_service = None
    wiring.tool_call_loop_guard.record_and_check.return_value = None
    phase_a = LlmPhaseAResult(
        player_id=PlayerId(3),
        prompt={"messages": [], "tool_runtime_context": None},
        tools_payload=[{"type": "function", "function": {"name": "interact"}}],
        tool_call={"name": "interact", "arguments": {}},
        exception=None,
    )

    phase_b.run_phase_b(wiring, phase_a)

    call = wiring.tool_call_loop_guard.record_and_check.call_args
    assert call.kwargs["result_summary"] == "麦束がありません。"
