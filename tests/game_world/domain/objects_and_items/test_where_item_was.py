from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.object_and_item.item_spec_declaration import Lasts
from ai_rpg_world.game_world.domain.exception.world_contents_exception import AggregateNotInWorldException
from ai_rpg_world.game_world.domain.objects_and_items import CarriedBy, Item, ItemInstanceId, ItemRanOutEvent, LyingAt
from ai_rpg_world.game_world.domain.value_object import DescriptionText, SpotId, Ticks, WorldTick
from tests.game_world.domain.effect._builders import ALICE, WORLD, inventory, item_spec
from tests.game_world.support.world_design_for_tests import spot
from tests.game_world.support.world_in_memory import world_in_memory

_PLAZA = SpotId("plaza")
_LAMP = replace(item_spec("lamp"), lasts=Lasts(Ticks(5), DescriptionText("ランプの油が切れた")))
_ROPE = item_spec("rope")
_LAMP_1 = ItemInstanceId("lamp#1")
_ROPE_1 = ItemInstanceId("rope#1")


def _alice_carrying(*items: tuple[ItemInstanceId, Item]) -> WorldSession:
    alice = inventory(ALICE)
    for item_id, item in items:
        alice.receive(item_id, item.spec_id)
    return world_in_memory(
        world=WORLD,
        people=(ALICE,),
        spots=(spot(_PLAZA.value),),
        item_specs=(_LAMP, _ROPE),
        inventories=(alice,),
        items=tuple(item for _, item in items),
    )


def _lamp() -> tuple[ItemInstanceId, Item]:
    return _LAMP_1, Item.come_into_world(_LAMP_1, _LAMP, WorldTick(0))


def _rope() -> tuple[ItemInstanceId, Item]:
    return _ROPE_1, Item.come_into_world(_ROPE_1, _ROPE, WorldTick(0))


def _ran_out(world: WorldSession) -> list[tuple[ItemInstanceId, object, WorldTick]]:
    return [(event.item, event.where, event.at) for event in world.commit() if isinstance(event, ItemRanOutEvent)]


class TestCarriedByRunOutAgedItems:
    """CarriedBy.run_out_aged_items が、持つ時間の過ぎた品物を荷から外し、切らして、世界から出すことを保証する。"""

    def test_aged_item_leaves_the_pack_and_runs_out_in_the_name_of_the_carrier(self) -> None:
        """5 tick 持つランプを持ったアリスの荷で tick 5 に切らすと、ランプは荷から外れ、ItemRanOutEvent がアリスの名で出る。"""
        world = _alice_carrying(_lamp())

        CarriedBy(ALICE).run_out_aged_items(world.aggregates(), WorldTick(5))

        assert world.aggregates().inventory(ALICE).items() == ()
        assert _ran_out(world) == [(_LAMP_1, CarriedBy(ALICE), WorldTick(5))]

    def test_item_that_ran_out_is_taken_out_of_the_world(self) -> None:
        """切れたランプは世界から出て、引こうとすると AggregateNotInWorldException で断られる。"""
        world = _alice_carrying(_lamp())

        CarriedBy(ALICE).run_out_aged_items(world.aggregates(), WorldTick(5))

        with pytest.raises(AggregateNotInWorldException):
            world.aggregates().item(_LAMP_1)

    def test_item_with_time_left_stays_in_the_pack(self) -> None:
        """tick 4 ではランプの時間が残っているので、荷に残り、ItemRanOutEvent も出ない。"""
        world = _alice_carrying(_lamp())

        CarriedBy(ALICE).run_out_aged_items(world.aggregates(), WorldTick(4))

        assert world.aggregates().inventory(ALICE).items() == (_LAMP_1,)
        assert _ran_out(world) == []

    def test_only_the_aged_item_leaves_and_the_lasting_one_stays(self) -> None:
        """縄とランプを持つ荷で tick 5 に切らすと、ランプだけが切れ、持つ時間の無い縄は残る。"""
        world = _alice_carrying(_rope(), _lamp())

        CarriedBy(ALICE).run_out_aged_items(world.aggregates(), WorldTick(5))

        assert world.aggregates().inventory(ALICE).items() == (_ROPE_1,)
        assert [item for item, _, _ in _ran_out(world)] == [_LAMP_1]


class TestLyingAtRunOutAgedItems:
    """LyingAt.run_out_aged_items が、持つ時間の過ぎた品物を地面から外し、場所の名で切らすことを保証する。"""

    def test_aged_item_leaves_the_ground_and_runs_out_in_the_name_of_the_spot(self) -> None:
        """広場の地面に置いたランプを tick 5 に切らすと、地面から外れ、ItemRanOutEvent が広場の名で出る。"""
        world = _alice_carrying(_lamp())
        world.aggregates().inventory(ALICE).give_up(_LAMP_1)
        world.aggregates().ground_items(_PLAZA).place(_LAMP_1)

        LyingAt(_PLAZA).run_out_aged_items(world.aggregates(), WorldTick(5))

        assert world.aggregates().ground_items(_PLAZA).items() == ()
        assert _ran_out(world) == [(_LAMP_1, LyingAt(_PLAZA), WorldTick(5))]

    def test_item_carried_by_someone_is_left_alone(self) -> None:
        """アリスが持っているランプは、広場の地面を切らしても切れず、荷に残る。"""
        world = _alice_carrying(_lamp())

        LyingAt(_PLAZA).run_out_aged_items(world.aggregates(), WorldTick(5))

        assert world.aggregates().inventory(ALICE).items() == (_LAMP_1,)
        assert _ran_out(world) == []
