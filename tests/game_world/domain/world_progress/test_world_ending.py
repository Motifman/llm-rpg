from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.world_progress_exception import WorldAlreadyEndedException
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from ai_rpg_world.game_world.domain.world_progress import WorldEndedEvent, WorldEnding

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
