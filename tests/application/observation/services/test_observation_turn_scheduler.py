"""ObservationTurnScheduler のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _output(schedules_turn: bool = False) -> ObservationOutput:
    """テスト用 ObservationOutput"""
    return ObservationOutput(
        prose="test",
        structured={},
        schedules_turn=schedules_turn,
        breaks_movement=False,
    )


class TestObservationTurnSchedulerNormal:
    """maybe_schedule のテスト（正常）"""

    def test_calls_schedule_turn_when_schedules_turn_and_llm_player(self):
        """schedules_turn=True かつ LLM 制御プレイヤーのとき schedule_turn が呼ばれる"""
        turn_trigger = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_resolver,
        )
        output = _output(schedules_turn=True)

        service.maybe_schedule(PlayerId(1), output)

        turn_trigger.schedule_turn.assert_called_once_with(PlayerId(1))
        llm_resolver.is_llm_controlled.assert_called_once_with(PlayerId(1))

    def test_does_not_call_when_schedules_turn_false(self):
        """schedules_turn=False のとき schedule_turn は呼ばれない"""
        turn_trigger = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_resolver,
        )
        output = _output(schedules_turn=False)

        service.maybe_schedule(PlayerId(1), output)

        turn_trigger.schedule_turn.assert_not_called()
        llm_resolver.is_llm_controlled.assert_not_called()

    def test_does_not_call_when_not_llm_controlled(self):
        """LLM 制御でないプレイヤーのとき schedule_turn は呼ばれない"""
        turn_trigger = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = False
        service = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_resolver,
        )
        output = _output(schedules_turn=True)

        service.maybe_schedule(PlayerId(1), output)

        turn_trigger.schedule_turn.assert_not_called()
        llm_resolver.is_llm_controlled.assert_called_once_with(PlayerId(1))


class TestObservationTurnSchedulerBoundary:
    """境界条件のテスト"""

    def test_does_not_call_when_turn_trigger_none(self):
        """turn_trigger が None のとき schedule_turn は呼ばれない"""
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = ObservationTurnScheduler(
            turn_trigger=None,
            llm_player_resolver=llm_resolver,
        )
        output = _output(schedules_turn=True)

        service.maybe_schedule(PlayerId(1), output)

        llm_resolver.is_llm_controlled.assert_not_called()

    def test_does_not_call_when_llm_player_resolver_none(self):
        """llm_player_resolver が None のとき schedule_turn は呼ばれない"""
        turn_trigger = MagicMock()
        service = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=None,
        )
        output = _output(schedules_turn=True)

        service.maybe_schedule(PlayerId(1), output)

        turn_trigger.schedule_turn.assert_not_called()

    def test_does_not_raise_when_both_none(self):
        """turn_trigger と llm_player_resolver が両方 None でも例外にならない"""
        service = ObservationTurnScheduler(
            turn_trigger=None,
            llm_player_resolver=None,
        )
        output = _output(schedules_turn=True)

        service.maybe_schedule(PlayerId(1), output)  # 例外なし

    def test_calls_for_multiple_players(self):
        """複数プレイヤーに対して順に schedule_turn が呼ばれる"""
        turn_trigger = MagicMock()
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_resolver,
        )
        output = _output(schedules_turn=True)

        service.maybe_schedule(PlayerId(1), output)
        service.maybe_schedule(PlayerId(2), output)

        assert turn_trigger.schedule_turn.call_count == 2
        turn_trigger.schedule_turn.assert_any_call(PlayerId(1))
        turn_trigger.schedule_turn.assert_any_call(PlayerId(2))


class TestObservationTurnSchedulerExceptions:
    """例外伝播のテスト"""

    def test_propagates_exception_when_schedule_turn_raises(self):
        """schedule_turn が例外を投げた場合、その例外が伝播する"""
        turn_trigger = MagicMock()
        turn_trigger.schedule_turn.side_effect = RuntimeError("schedule failed")
        llm_resolver = MagicMock()
        llm_resolver.is_llm_controlled.return_value = True
        service = ObservationTurnScheduler(
            turn_trigger=turn_trigger,
            llm_player_resolver=llm_resolver,
        )
        output = _output(schedules_turn=True)

        with pytest.raises(RuntimeError, match="schedule failed"):
            service.maybe_schedule(PlayerId(1), output)

        turn_trigger.schedule_turn.assert_called_once_with(PlayerId(1))
