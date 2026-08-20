"""予約中のアイテムは、通常の消費対象として選ばれない。

取引に出した品は「持っているが今は使えない」状態になる。ここを素通しすると、
提案中の品を食べたり渡したりできてしまい、承諾した相手から見て「受けたのに
何も来なかった」になる。失敗が相手の行動に依存して読めなくなるので、探す
段階で避ける。

**「無い」と「予約されている」は呼び出し側で言い分けたい**ので、探索結果は
両者を区別して返す。
"""

from __future__ import annotations

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.inventory_item_appearance import (
    InventoryItemAppearance,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId

_SPEC = ItemSpecId.create(10)


def _appearances(
    instances: dict[int, tuple[int, bool]],
) -> dict[ItemInstanceId, InventoryItemAppearance]:
    return {
        ItemInstanceId(iid): InventoryItemAppearance(
            item_spec_id=ItemSpecId.create(spec_id),
            is_spoiled=spoiled,
        )
        for iid, (spec_id, spoiled) in instances.items()
    }


def _inventory_with(instance_ids: list[int]) -> PlayerInventoryAggregate:
    inv = PlayerInventoryAggregate(player_id=PlayerId(1), max_slots=5)
    for value in instance_ids:
        inv.acquire_item(ItemInstanceId(value), item_spec_id_value=10)
    return inv


class TestReservedItemsAreNotOffered:
    """予約中の品は消費対象として返らない。"""

    def test_an_unreserved_item_is_found(self) -> None:
        """予約されていない品はこれまでどおり見つかる。"""
        inv = _inventory_with([100])
        appearances = _appearances({100: (10, False)})

        found = inv.find_available_slot_by_item_spec_id_and_spoilage(
            _SPEC, False, appearances,
        )

        assert found.slot_id is not None
        assert found.blocked_by_reservation is False

    def test_a_reserved_item_is_not_returned(self) -> None:
        """予約中の品しか無いときは、消費対象として返らない。"""
        inv = _inventory_with([100])
        inv.reserve_item(SlotId(0))
        appearances = _appearances({100: (10, False)})

        found = inv.find_available_slot_by_item_spec_id_and_spoilage(
            _SPEC, False, appearances,
        )

        assert found.slot_id is None

    def test_the_reason_says_it_is_reserved(self) -> None:
        """予約中で見つからなかったことを、持っていない場合と区別して返す。

        呼び出し側が「持っていない」と「取引に出している」を言い分けるため。
        """
        inv = _inventory_with([100])
        inv.reserve_item(SlotId(0))
        appearances = _appearances({100: (10, False)})

        found = inv.find_available_slot_by_item_spec_id_and_spoilage(
            _SPEC, False, appearances,
        )

        assert found.blocked_by_reservation is True

    def test_not_owning_it_is_not_reported_as_reserved(self) -> None:
        """そもそも持っていないときは、予約が理由だとは言わない。"""
        inv = _inventory_with([])
        appearances = _appearances({})

        found = inv.find_available_slot_by_item_spec_id_and_spoilage(
            _SPEC, False, appearances,
        )

        assert found.slot_id is None
        assert found.blocked_by_reservation is False

    def test_an_unreserved_copy_is_preferred_over_a_reserved_one(self) -> None:
        """同じ品を 2 つ持ち片方だけ予約中なら、予約されていない方が返る。"""
        inv = _inventory_with([100, 101])
        inv.reserve_item(SlotId(0))
        appearances = _appearances({100: (10, False), 101: (10, False)})

        found = inv.find_available_slot_by_item_spec_id_and_spoilage(
            _SPEC, False, appearances,
        )

        assert found.slot_id == SlotId(1)
        assert found.blocked_by_reservation is False

    def test_spoilage_is_still_matched(self) -> None:
        """腐敗状態の一致判定は、予約を見るようになっても変わらない。"""
        inv = _inventory_with([100])
        appearances = _appearances({100: (10, True)})

        assert (
            inv.find_available_slot_by_item_spec_id_and_spoilage(
                _SPEC, False, appearances,
            ).slot_id
            is None
        )
        assert (
            inv.find_available_slot_by_item_spec_id_and_spoilage(
                _SPEC, True, appearances,
            ).slot_id
            is not None
        )
