from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.action_exception import UndeclaredNounException
from ai_rpg_world.game_world.domain.exception.game_world_exception import RepeatedMementoKeyException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    GroundItemAlreadyPlacedException,
    GroundItemNotFoundException,
)
from ai_rpg_world.game_world.domain.objects_and_items import (
    GroundItemPlacedEvent,
    GroundItems,
    GroundItemsMemento,
    GroundItemTakenEvent,
    ItemInstanceId,
)
from ai_rpg_world.game_world.domain.value_object import SpotId
from tests.game_world.support.memento_for_tests import rebuilt_from_memento
from tests.game_world.support.world_design_for_tests import character, compose_world, nouns, spot

_SQUARE = SpotId("square")
_LANTERN = ItemInstanceId("lantern#1")
_PICKAXE = ItemInstanceId("pickaxe#1")
_DESIGN = compose_world(nouns(spots=(spot("square"),), characters=(character("alice", "square"),)))


class TestGroundItems:
    """GroundItems が、場所の地面にある品物を置いた順に持ち、置く・拾うたびにイベントをためることを保証する。"""

    def test_starts_empty_for_its_spot(self) -> None:
        """作った直後は、自分の場所の ID を持ち、地面に品物が無い。"""
        ground = GroundItems.start(_SQUARE)

        assert ground.spot_id == _SQUARE
        assert ground.items() == ()
        assert not ground.contains(_LANTERN)

    def test_place_puts_items_in_placed_order_and_records_event(self) -> None:
        """place した品物は置いた順に items に並び、1 つごとに GroundItemPlacedEvent がたまる。"""
        ground = GroundItems.start(_SQUARE)

        ground.place(_LANTERN)
        ground.place(_PICKAXE)

        assert ground.items() == (_LANTERN, _PICKAXE)
        assert ground.contains(_PICKAXE)
        events = ground.get_events()
        assert [type(event) for event in events] == [GroundItemPlacedEvent, GroundItemPlacedEvent]
        assert (events[0].spot_id, events[0].item) == (_SQUARE, _LANTERN)

    def test_take_removes_item_and_records_event(self) -> None:
        """take した品物は地面から無くなり、GroundItemTakenEvent がたまる。"""
        ground = GroundItems.start(_SQUARE)
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
        ground = GroundItems.start(_SQUARE)
        ground.place(_LANTERN)
        ground.clear_events()

        with pytest.raises(GroundItemAlreadyPlacedException):
            ground.place(_LANTERN)

        assert ground.items() == (_LANTERN,)
        assert ground.get_events() == []

    def test_taking_an_item_not_on_the_ground_is_refused(self) -> None:
        """地面に無い品物を take すると GroundItemNotFoundException を投げ、イベントはたまらない。"""
        ground = GroundItems.start(_SQUARE)

        with pytest.raises(GroundItemNotFoundException):
            ground.take(_LANTERN)

        assert ground.get_events() == []


class TestGroundItemsMemento:
    """GroundItems を memento から作り直すと、地面の品物が置いた順のまま同じで、イベントは出ず、宣言に無い場所の地面は読まないことを保証する。"""

    def test_rebuilt_ground_keeps_items_in_placed_order(self) -> None:
        """つるはし・カンテラの順に置き、もう 1 つ置いて拾ったあと作り直すと、つるはし・カンテラの順で地面にある。"""
        rope = ItemInstanceId("rope#1")
        ground = GroundItems.start(_SQUARE)
        ground.place(_PICKAXE)
        ground.place(rope)
        ground.place(_LANTERN)
        ground.take(rope)

        rebuilt = rebuilt_from_memento(ground, _DESIGN.nouns)

        assert rebuilt.memento() == ground.memento()
        assert rebuilt.memento() != GroundItems.start(_SQUARE).memento()
        assert rebuilt.spot_id == _SQUARE
        assert rebuilt.items() == (_PICKAXE, _LANTERN)
        assert not rebuilt.contains(rope)

    def test_rebuilding_records_no_event(self) -> None:
        """品物を置いたあとの memento から作り直しても、作り直したものはイベントをためていない。"""
        ground = GroundItems.start(_SQUARE)
        ground.place(_LANTERN)

        assert rebuilt_from_memento(ground, _DESIGN.nouns).get_events() == []

    def test_same_item_twice_is_refused(self) -> None:
        """カンテラが 2 度ある memento を作ると、RepeatedMementoKeyException を投げる。"""
        with pytest.raises(RepeatedMementoKeyException):
            GroundItemsMemento(spot_id=_SQUARE, items=(_LANTERN, _LANTERN))

    def test_ground_at_undeclared_spot_is_refused(self) -> None:
        """宣言に無い場所 moon の地面の memento から作り直すと、UndeclaredNounException を投げる。"""
        memento = GroundItemsMemento(spot_id=SpotId("moon"), items=(_LANTERN,))

        with pytest.raises(UndeclaredNounException):
            GroundItems.from_memento(memento, _DESIGN.nouns)


class TestGroundItemsStartsOnlyInReachableState:
    """GroundItems は、置く操作では作れない地面から始まらないことを保証する。"""

    def test_same_item_twice_is_refused_by_constructor(self) -> None:
        """カンテラを 2 度置いた地面を直に作ると、GroundItemAlreadyPlacedException を投げる。"""
        with pytest.raises(GroundItemAlreadyPlacedException):
            GroundItems(_SQUARE, items=(_LANTERN, _LANTERN))
