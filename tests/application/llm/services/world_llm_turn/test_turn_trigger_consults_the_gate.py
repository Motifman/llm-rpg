"""run_scheduled_turns が、回す前に門へ pending を渡し、返された人だけを回す。"""

from __future__ import annotations

from unittest.mock import MagicMock

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (
    WorldLlmTurnTrigger,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _wiring(gate) -> MagicMock:
    wiring = MagicMock()
    wiring.runtime.check_game_end.return_value.is_ended = False
    wiring.runtime._runtime_config.llm_turn_parallel_workers = 0
    wiring.runtime._runtime_config.llm_meeting_serial_turns = False
    wiring.turn_gate = gate
    wiring.run_turn.return_value = LlmCommandResultDto(success=True, message="ok")
    return wiring


def _trigger(gate) -> WorldLlmTurnTrigger:
    trigger = WorldLlmTurnTrigger(wiring=_wiring(gate))
    trigger._can_player_act = lambda pid: True  # type: ignore[method-assign]
    return trigger


class TestTheTriggerRunsOnlyWhoTheGateReturns:
    def test_players_the_gate_drops_are_not_run(self) -> None:
        """門が返さなかった人は run_turn されず、返した人だけが回る。"""
        gate = MagicMock()
        gate.candidates.side_effect = lambda ids: list(ids)
        gate.decide_wave.return_value = [PlayerId(2)]
        trigger = _trigger(gate)
        trigger.schedule_turn(PlayerId(1)); trigger.schedule_turn(PlayerId(2))

        trigger.run_scheduled_turns()

        assert set(gate.decide_wave.call_args[0][0]) == {PlayerId(1), PlayerId(2)}
        trigger.wiring.run_turn.assert_called_once_with(PlayerId(2))
        assert trigger.pending_player_ids == set()

    def test_without_a_gate_everyone_pending_runs(self) -> None:
        """門が無ければ pending の全員が回る (**正の対照**)。"""
        trigger = _trigger(None)
        trigger.schedule_turn(PlayerId(1)); trigger.schedule_turn(PlayerId(2))

        trigger.run_scheduled_turns()

        assert trigger.wiring.run_turn.call_count == 2

    def test_when_the_gate_drops_everyone_nothing_runs(self) -> None:
        """門が誰も返さなければ、この tick は誰も回らない。"""
        gate = MagicMock(); gate.candidates.side_effect = lambda ids: list(ids); gate.decide_wave.return_value = []
        trigger = _trigger(gate)
        trigger.schedule_turn(PlayerId(1))

        trigger.run_scheduled_turns()

        trigger.wiring.run_turn.assert_not_called()


class TestTheTriggerWidensCandidatesThroughTheGate:
    def test_candidates_come_from_the_gate_and_scheduled_players_are_passed_along(self) -> None:
        """trigger は候補を門に広げさせ、pending に居た人を scheduled として門に渡す。"""
        gate = MagicMock()
        gate.candidates.return_value = [PlayerId(1), PlayerId(3)]
        gate.decide_wave.return_value = [PlayerId(3)]
        trigger = _trigger(gate)
        trigger.schedule_turn(PlayerId(1))

        trigger.run_scheduled_turns()

        assert list(gate.candidates.call_args[0][0]) == [PlayerId(1)]
        assert list(gate.decide_wave.call_args[0][0]) == [PlayerId(1), PlayerId(3)]
        assert list(gate.decide_wave.call_args[1]["scheduled"]) == [PlayerId(1)]
        trigger.wiring.run_turn.assert_called_once_with(PlayerId(3))
