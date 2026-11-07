from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.whereabouts_exception import (
    BrokenRouteException,
    EmptyRouteException,
)
from ai_rpg_world.game_world.domain.value_object import SpotId
from ai_rpg_world.game_world.domain.whereabouts import Route
from tests.game_world.domain.whereabouts._builders import path


class TestRouteDirection:
    """Route が、出発点から通路を順にたどって、各区間の向きと行き先を決めることを保証する。"""

    def test_single_two_way_passage_can_be_walked_from_either_end(self) -> None:
        """両方向に通れる通路 1 本の Route は、start を ends の後ろの端にすると、行き先が前の端になる。"""
        shaft = path("shaft", "mine_entrance", "mine_depths")

        back = Route(start=SpotId("mine_depths"), legs=(shaft,))

        assert back.destination == SpotId("mine_entrance")

    def test_destination_follows_every_leg_from_the_start(self) -> None:
        """通路を 2 本つないだ Route の行き先は、出発点から 2 本をたどった先の場所になる。"""
        route = Route(
            start=SpotId("plaza"),
            legs=(path("street", "plaza", "well"), path("lane", "mine_entrance", "well")),
        )

        assert route.destination == SpotId("mine_entrance")

    def test_end_of_leg_is_the_spot_reached_after_walking_that_leg(self) -> None:
        """end_of_leg(i) は、i 番目の区間を歩き終えたときにいる場所を返す。"""
        route = Route(
            start=SpotId("plaza"),
            legs=(path("street", "plaza", "well"), path("lane", "well", "mine_entrance")),
        )

        assert (route.end_of_leg(0), route.end_of_leg(1)) == (SpotId("well"), SpotId("mine_entrance"))


class TestRouteRejectsImpossibleWalks:
    """たどれない Route を作れないことを保証する。"""

    def test_route_without_legs_is_rejected(self) -> None:
        """区間が 0 本の Route は EmptyRouteException を投げる。"""
        with pytest.raises(EmptyRouteException):
            Route(start=SpotId("plaza"), legs=())

    def test_leg_that_does_not_touch_the_current_spot_is_rejected(self) -> None:
        """前の区間の着いた場所を端に持たない区間があると、BrokenRouteException を投げる。"""
        with pytest.raises(BrokenRouteException):
            Route(
                start=SpotId("plaza"),
                legs=(path("street", "plaza", "well"), path("tunnel", "cellar", "mine_depths")),
            )

    def test_one_way_passage_walked_backwards_is_rejected(self) -> None:
        """片道の通路を ends の後ろの端から歩く Route は、BrokenRouteException を投げる。"""
        slide = path("slide", "cliff_top", "beach", two_way=False)

        with pytest.raises(BrokenRouteException):
            Route(start=SpotId("beach"), legs=(slide,))

    def test_one_way_passage_walked_forwards_is_accepted(self) -> None:
        """片道の通路を ends の前の端から歩く Route は作れ、行き先は後ろの端になる。"""
        slide = path("slide", "cliff_top", "beach", two_way=False)

        route = Route(start=SpotId("cliff_top"), legs=(slide,))

        assert route.destination == SpotId("beach")
