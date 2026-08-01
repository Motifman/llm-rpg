"""修正可能な行動失敗が既存の本人向け観測から次ターンを予約することを保証する。"""

from __future__ import annotations

from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    is_reschedulable_error_code,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring


class TestRecoverableActionFailureCodes:
    """プロンプト内の情報で直せる interact 失敗を次ターン予約の対象として固定する。"""

    def test_interaction_precondition_failed_is_reschedulable(self) -> None:
        """前提不足は失敗理由を読んで別行動へ切り替えられるため次ターンを予約する。"""
        assert is_reschedulable_error_code("INTERACTION_PRECONDITION_FAILED")

    def test_invalid_target_label_is_reschedulable(self) -> None:
        """対象名の未解決は移動先名の未解決と同様に候補から直せるため次ターンを予約する。"""
        assert is_reschedulable_error_code("INVALID_TARGET_LABEL")

    def test_interaction_action_not_found_is_reschedulable(self) -> None:
        """未定義 action は返された利用可能一覧から選び直せるため次ターンを予約する。"""
        assert is_reschedulable_error_code("INTERACTION_ACTION_NOT_FOUND")


def test_common_tool_exit_applies_reschedule_policy_to_handler_result() -> None:
    """handler がフラグを立て忘れても共通出口が allowlist を DTO へ反映する。"""
    wiring = object.__new__(_WorldLlmWiring)
    wiring._tool_handlers = {
        "interact": lambda _player_id, _arguments, _context: LlmCommandResultDto(
            success=False,
            message="流木が足りない。3本は要る。",
            error_code="INTERACTION_PRECONDITION_FAILED",
        )
    }

    result = wiring._execute_tool(PlayerId(1), "interact", {}, None)

    assert result.should_reschedule is True
