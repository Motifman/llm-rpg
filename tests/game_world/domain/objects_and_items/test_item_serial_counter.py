"""ItemSerialCounter が、世界に持ち込む品物に世界の中の通し番号から ID を振ることを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.objects_and_items import ItemSerialCounter, ItemSerialCounterMemento
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from tests.game_world.support.world_design_for_tests import item_spec

_WORLD = WorldId("island")
_ROPE = item_spec("rope")


class TestItemSerialCounter:
    """持ち込んだ品物の ID が、番号の帳簿の中身だけで決まることを保証する。"""

    def test_two_items_brought_into_one_world_get_different_ids(self) -> None:
        """同じ世界で同じ品物を 2 つ持ち込むと、2 つは別の ID になる。"""
        counter = ItemSerialCounter.start(_WORLD)

        first = counter.bring_item_into_world(_ROPE, WorldTick(0))
        second = counter.bring_item_into_world(_ROPE, WorldTick(0))

        assert first.item_id != second.item_id

    def test_counters_with_the_same_history_give_the_same_ids(self) -> None:
        """始めたばかりの帳簿 2 つに同じ順で品物を持ち込むと、同じ順に同じ ID が出る。"""
        one, other = ItemSerialCounter.start(_WORLD), ItemSerialCounter.start(_WORLD)

        ids_in_one = [one.bring_item_into_world(_ROPE, WorldTick(tick)).item_id for tick in range(3)]
        ids_in_other = [other.bring_item_into_world(_ROPE, WorldTick(tick)).item_id for tick in range(3)]

        assert ids_in_one == ids_in_other

    def test_counter_rebuilt_from_memento_continues_after_the_last_id(self) -> None:
        """持ち込んだあとの memento から作り直した帳簿は、それまでに出したどの ID とも違う ID を出す。"""
        counter = ItemSerialCounter.start(_WORLD)
        issued = {counter.bring_item_into_world(_ROPE, WorldTick(0)).item_id for _ in range(2)}

        rebuilt = ItemSerialCounter.from_memento(counter.memento())

        assert rebuilt.bring_item_into_world(_ROPE, WorldTick(1)).item_id not in issued

    def test_memento_with_a_negative_count_is_refused(self) -> None:
        """出した数が負の memento は ValueOutOfRangeException で止まる。"""
        with pytest.raises(ValueOutOfRangeException):
            ItemSerialCounterMemento(world_id=_WORLD, issued=-1)
