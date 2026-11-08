from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    GroundItemAlreadyPlacedException,
    GroundItemNotFoundException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItemPlacedEvent,
    GroundItems,
    GroundItemTakenEvent,
    ItemInstanceId,
)
from ai_rpg_world.game_world.domain.value_object import SpotId

_SQUARE = SpotId("square")
_LANTERN = ItemInstanceId("lantern#1")
_PICKAXE = ItemInstanceId("pickaxe#1")


class TestGroundItems:
    """GroundItems が、場所の地面にある品物を置いた順に持ち、置く・拾うたびにイベントをためることを保証する。"""

    def test_starts_empty_for_its_spot(self) -> None:
        """作った直後は、自分の場所の ID を持ち、地面に品物が無い。"""
        ground = GroundItems(_SQUARE)

        assert ground.spot_id == _SQUARE
        assert ground.items() == ()
        assert not ground.contains(_LANTERN)

    def test_place_puts_items_in_placed_order_and_records_event(self) -> None:
        """place した品物は置いた順に items に並び、1 つごとに GroundItemPlacedEvent がたまる。"""
        ground = GroundItems(_SQUARE)

        ground.place(_LANTERN)
        ground.place(_PICKAXE)

        assert ground.items() == (_LANTERN, _PICKAXE)
        assert ground.contains(_PICKAXE)
        events = ground.get_events()
        assert [type(event) for event in events] == [GroundItemPlacedEvent, GroundItemPlacedEvent]
        assert (events[0].spot_id, events[0].item) == (_SQUARE, _LANTERN)

    def test_take_removes_item_and_records_event(self) -> None:
        """take した品物は地面から無くなり、GroundItemTakenEvent がたまる。"""
        ground = GroundItems(_SQUARE)
        ground.place(_LANTERN)
        ground.place(_PICKAXE)
        ground.clear_events()

        ground.take(_LANTERN)

        assert ground.items() == (_PICKAXE,)
        assert not ground.contains(_LANTERN)
        [event] = ground.get_events()
        assert isinstance(event, GroundItemTakenEvent)
        assert (event.spot_id, event.item) == (_SQUARE, _LANTERN)

    def test_placing_an_item_already_on_the_ground_is_refused(self) -> None:
        """地面にある品物をもう一度 place すると GroundItemAlreadyPlacedException を投げ、品物もイベントも増えない。"""
        ground = GroundItems(_SQUARE)
        ground.place(_LANTERN)
        ground.clear_events()

        with pytest.raises(GroundItemAlreadyPlacedException):
            ground.place(_LANTERN)

        assert ground.items() == (_LANTERN,)
        assert ground.get_events() == []

    def test_taking_an_item_not_on_the_ground_is_refused(self) -> None:
        """地面に無い品物を take すると GroundItemNotFoundException を投げ、イベントはたまらない。"""
        ground = GroundItems(_SQUARE)

        with pytest.raises(GroundItemNotFoundException):
            ground.take(_LANTERN)

        assert ground.get_events() == []
