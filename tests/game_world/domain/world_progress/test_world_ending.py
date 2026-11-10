from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.world_progress_exception import WorldAlreadyEndedException
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_progress import WorldEndedEvent, WorldEnding
from tests.game_world.support.memento_for_tests import rebuilt_from_memento

_WORLD = WorldId("station")


class TestWorldEnding:
    """WorldEnding.end が世界を一度だけ終え、終わったことをイベントにためることを保証する。"""

    def test_world_has_not_ended_at_first(self) -> None:
        """作ったばかりの世界は、まだ終わっていない。"""
        assert WorldEnding(_WORLD).has_ended() is False

    def test_end_records_world_ended_event(self) -> None:
        """tick 40 で end すると has_ended は真になり、世界と tick 40 を持つ WorldEndedEvent をためる。"""
        ending = WorldEnding(_WORLD)

        ending.end(WorldTick(40))

        assert ending.has_ended() is True
        [event] = ending.get_events()
        assert isinstance(event, WorldEndedEvent)
        assert (event.world_id, event.at) == (_WORLD, WorldTick(40))

    def test_ending_ended_world_again_raises_and_records_nothing(self) -> None:
        """一度終わった世界をもう一度 end すると WorldAlreadyEndedException を投げ、イベントを足さない。"""
        ending = WorldEnding(_WORLD)
        ending.end(WorldTick(40))

        with pytest.raises(WorldAlreadyEndedException):
            ending.end(WorldTick(41))

        assert len(ending.get_events()) == 1


class TestWorldEndingMemento:
    """WorldEnding を memento から作り直すと、終わったかどうかが元と同じになり、イベントは出ないことを保証する。"""

    def test_rebuilt_ending_has_ended(self) -> None:
        """tick 9 に終わった世界の終わりを作り直すと、終わっている。"""
        ending = WorldEnding(_WORLD)
        ending.end(WorldTick(9))

        rebuilt = rebuilt_from_memento(ending)

        assert rebuilt.memento() == ending.memento()
        assert rebuilt.has_ended()
        assert rebuilt.world_id == _WORLD

    def test_rebuilt_ending_refuses_to_end_again(self) -> None:
        """終わった世界の終わりを作り直してから end すると、WorldAlreadyEndedException を投げる。"""
        ending = WorldEnding(_WORLD)
        ending.end(WorldTick(9))
        rebuilt = rebuilt_from_memento(ending)

        with pytest.raises(WorldAlreadyEndedException):
            rebuilt.end(WorldTick(10))

    def test_rebuilding_records_no_event(self) -> None:
        """終わったあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        ending = WorldEnding(_WORLD)
        ending.end(WorldTick(9))

        assert rebuilt_from_memento(ending).get_events() == []
