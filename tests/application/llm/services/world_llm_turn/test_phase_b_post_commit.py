"""Phase Bが未処理の確定後例外を通常失敗へ縮退させないことを保証する。"""

from unittest.mock import MagicMock

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.llm.services.world_llm_turn import phase_b
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def test_unhandled_post_commit_exception_is_committed_success(monkeypatch) -> None:
    """個別executorが例外を通しても成功を維持し、移動状態を失敗復元しない。"""
    post_commit_error = CommandPostCommitException(handoff_error=RuntimeError("delivery failed"))

    def _raise_post_commit(*args, **kwargs):
        raise post_commit_error

    restore_nav_state = MagicMock()
    monkeypatch.setattr(phase_b, "execute_tool", _raise_post_commit)
    monkeypatch.setattr(
        phase_b,
        "maybe_interrupt_busy",
        MagicMock(return_value=(True, object())),
    )
    monkeypatch.setattr(phase_b, "restore_nav_state", restore_nav_state)
    monkeypatch.setattr(
        phase_b,
        "record_prompt_dataset_turn_result",
        MagicMock(),
    )

    wiring = MagicMock()
    wiring.runtime.trace_recorder = None
    wiring.memo_completion_hint_service = None
    wiring.tool_call_loop_guard.record_and_check.return_value = None
    phase_a = LlmPhaseAResult(
        player_id=PlayerId(1),
        prompt={"messages": [], "tool_runtime_context": None},
        tools_payload=[{"type": "function", "function": {"name": "test_tool"}}],
        tool_call={"name": "test_tool", "arguments": {}},
        exception=None,
    )

    result = phase_b.run_phase_b(wiring, phase_a)

    assert result.success is True
    assert result.error_code == "COMMAND_COMMITTED_POST_PROCESSING_FAILED"
    assert result.should_reschedule is False
    assert "反映済み" in result.message
    assert "再試行" not in result.message
    restore_nav_state.assert_not_called()
    wiring.runtime._record_action_result.assert_called_once()
    assert wiring.runtime._record_action_result.call_args.kwargs["success"] is True
