from __future__ import annotations

from ai_rpg_world.game_world.application.accept_world_time_passage import WorldTimePassageRefused, WorldTimePassed
from ai_rpg_world.game_world.domain.value_object import Ticks
from tests.game_world.application.world_for_accepting_tests import GUST, WORLD_ENDED, WorldForAccepting


class TestAcceptWorldTimePassage:
    """AcceptWorldTimePassage が、時間を 1 つ進めて落ち着かせ、世界が終わったあとは断ることを保証する。"""

    def test_passing_time_advances_clock_and_settles_chance_happenings(self) -> None:
        """時間を進めると WorldTimePassed が返り、時計が 1 進み、時間のあとにだけ確かめる偶然の風の出来事が発火する。"""
        world = WorldForAccepting()
        before = world.now()

        reply = world.pass_time()

        assert reply == WorldTimePassed()
        assert world.now() == before + Ticks(1)
        assert world.is_raised(GUST) is True

    def test_passing_time_after_world_ended_is_refused_and_clock_stays(self) -> None:
        """世界が終わったあとに時間を進めようとすると WORLD_ALREADY_ENDED で断られ、時計は進まず、風も吹かず、何も配られない。"""
        world = WorldForAccepting()
        world.end_world()
        before = world.now()

        reply = world.pass_time()

        assert reply == WorldTimePassageRefused(WORLD_ENDED)
        assert world.now() == before
        assert world.is_raised(GUST) is False
        assert world.events == []
