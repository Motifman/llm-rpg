"""MovementInterruptionService のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.movement_interruption_service import (
    MovementInterruptionService,
)
from ai_rpg_world.application.world.contracts.commands import CancelMovementCommand
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _output(breaks_movement: bool = False, schedules_turn: bool = False) -> ObservationOutput:
    return ObservationOutput(
        prose="test",
        structured={"type": "test"},
        breaks_movement=breaks_movement,
        schedules_turn=schedules_turn,
    )


class TestMovementInterruptionServiceNormal:
    """maybe_cancel の正常系テスト"""

    def test_calls_cancel_movement_when_breaks_movement_and_llm_player(
        self,
    ):
        """breaks_movement=True かつ LLM 制御プレイヤーのとき cancel_movement が呼ばれる"""
        movement_service = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = MovementInterruptionService(
            movement_service=movement_service,
            llm_player_resolver=llm_resolver,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)

        movement_service.cancel_movement.assert_called_once()
        call_arg = movement_service.cancel_movement.call_args[0][0]
        assert isinstance(call_arg, CancelMovementCommand)
        assert call_arg.player_id == 1

    def test_does_not_call_when_breaks_movement_false(self):
        """breaks_movement=False のとき cancel_movement は呼ばれない"""
        movement_service = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = MovementInterruptionService(
            movement_service=movement_service,
            llm_player_resolver=llm_resolver,
        )
        output = _output(breaks_movement=False)

        service.maybe_cancel(PlayerId(1), output)

        movement_service.cancel_movement.assert_not_called()

    def test_does_not_call_when_not_llm_controlled(self):
        """LLM 制御でないプレイヤーでは cancel_movement は呼ばれない"""
        movement_service = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = False
        service = MovementInterruptionService(
            movement_service=movement_service,
            llm_player_resolver=llm_resolver,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)

        movement_service.cancel_movement.assert_not_called()
        llm_resolver.is_llm_controlled.assert_called_once_with(PlayerId(1))


class TestMovementInterruptionServiceBoundary:
    """maybe_cancel の境界テスト（オプショナル依存が None）"""

    def test_does_not_call_when_movement_service_none(self):
        """movement_service が None のとき cancel_movement は呼ばれない"""
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = MovementInterruptionService(
            movement_service=None,
            llm_player_resolver=llm_resolver,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)

        llm_resolver.is_llm_controlled.assert_not_called()

    def test_does_not_call_when_llm_player_resolver_none(self):
        """llm_player_resolver が None のとき cancel_movement は呼ばれない"""
        movement_service = MagicMock()
        service = MovementInterruptionService(
            movement_service=movement_service,
            llm_player_resolver=None,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)

        movement_service.cancel_movement.assert_not_called()

    def test_does_not_raise_when_both_none(self):
        """両方 None でも例外にならない"""
        service = MovementInterruptionService(
            movement_service=None,
            llm_player_resolver=None,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)  # 例外なし


class TestMovementInterruptionServiceExceptions:
    """例外処理のテスト"""

    def test_swallows_exception_and_logs_warning_when_cancel_movement_raises(self):
        """cancel_movement が例外を投げた場合、警告ログを出し伝播しない"""
        movement_service = MagicMock()
        movement_service.cancel_movement.side_effect = RuntimeError("cancel failed")
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = MovementInterruptionService(
            movement_service=movement_service,
            llm_player_resolver=llm_resolver,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)  # 例外は伝播しない

        movement_service.cancel_movement.assert_called_once()

    def test_swallows_player_not_found_exception(self):
        """cancel_movement が PlayerNotFoundException を投げても伝播しない"""
        from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
            PlayerNotFoundException,
        )

        movement_service = MagicMock()
        movement_service.cancel_movement.side_effect = PlayerNotFoundException(999)
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = MovementInterruptionService(
            movement_service=movement_service,
            llm_player_resolver=llm_resolver,
        )
        output = _output(breaks_movement=True)

        service.maybe_cancel(PlayerId(1), output)  # 例外は伝播しない

        movement_service.cancel_movement.assert_called_once()
