from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.game_world.domain.value_object.readiness_to_act import FreeToAct
from ai_rpg_world.play_session.domain.play_session_exception import TurnRoundsNotFoundException
from ai_rpg_world.play_session.domain.turn_rounds import RoundCount, RoundOpenedEvent, TurnRounds, TurnRoundsEvent
from ai_rpg_world.play_session.infrastructure.in_memory_turn_rounds_repository import InMemoryTurnRoundsRepository

_WORLD = WorldId("mine#1")
_GEN = PersonId("gen")


def _rounds() -> TurnRounds:
    return TurnRounds(_WORLD, round_limit=RoundCount(10), wake_waiting_after=RoundCount(3))


class TestInMemoryTurnRoundsRepository:
    """InMemoryTurnRoundsRepository が、世界ごとに巡りを写しで出し入れし、ためたイベントを保存のときに渡すことを保証する。"""

    def test_rounds_not_saved_are_refused(self) -> None:
        """保存していない世界の巡りを get すると TurnRoundsNotFoundException を投げる。"""
        with pytest.raises(TurnRoundsNotFoundException):
            InMemoryTurnRoundsRepository().get(_WORLD)

    def test_save_hands_off_events_once(self) -> None:
        """巡りを開いて保存すると RoundOpenedEvent が 1 件渡り、もう一度保存しても重ねて渡らない。"""
        handed: list[TurnRoundsEvent] = []
        repository = InMemoryTurnRoundsRepository(handoff=handed.extend)
        rounds = _rounds()
        rounds.open_round({_GEN: FreeToAct()})

        repository.save(rounds)
        repository.save(repository.get(_WORLD))

        assert [type(e) for e in handed] == [RoundOpenedEvent]

    def test_changes_after_get_are_not_saved_until_save(self) -> None:
        """get した巡りを開いても、save するまでは、次に get した巡りは開いていない。"""
        repository = InMemoryTurnRoundsRepository()
        repository.save(_rounds())

        repository.get(_WORLD).open_round({_GEN: FreeToAct()})

        repository.get(_WORLD).open_round({_GEN: FreeToAct()})
