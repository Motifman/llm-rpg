from __future__ import annotations

from collections import Counter
from typing import FrozenSet, Mapping

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository


def collect_owned_item_spec_ids_from_inventory(
    inventory: PlayerInventoryAggregate,
    item_repository: ItemRepository,
) -> FrozenSet[ItemSpecId]:
    """インベントリ装備・スロットに載っているアイテムの ItemSpecId 集合。"""
    out: set[ItemSpecId] = set()
    for i in range(inventory.max_slots):
        sid = SlotId(i)
        iid = inventory.get_item_instance_id_by_slot(sid)
        if iid is None:
            continue
        agg = item_repository.find_by_id(iid)
        if agg is not None:
            out.add(agg.item_spec.item_spec_id)
    for est in EquipmentSlotType:
        iid = inventory.get_item_instance_id_by_equipment_slot(est)
        if iid is None:
            continue
        agg = item_repository.find_by_id(iid)
        if agg is not None:
            out.add(agg.item_spec.item_spec_id)
    return frozenset(out)


def count_owned_item_instances_by_spec(
    inventory: PlayerInventoryAggregate,
    item_repository: ItemRepository,
) -> Mapping[ItemSpecId, int]:
    """インベントリ内のアイテム instance を ItemSpecId 別に重複保持数で数える。

    `collect_owned_item_spec_ids_from_inventory` が frozenset を返して
    重複を潰すのに対し、こちらは「berry を 3 個持っている」を 3 として
    返す。HAS_ITEM precondition の数量チェックや REMOVE_ITEM の
    複数消費判定で利用する。

    instance.quantity（同一 instance 内の stack 数）は加算しない。
    1 instance = 1 個として数える Phase 2-A の方針に従う。
    """
    counts: Counter[ItemSpecId] = Counter()
    for i in range(inventory.max_slots):
        sid = SlotId(i)
        iid = inventory.get_item_instance_id_by_slot(sid)
        if iid is None:
            continue
        agg = item_repository.find_by_id(iid)
        if agg is not None:
            counts[agg.item_spec.item_spec_id] += 1
    for est in EquipmentSlotType:
        iid = inventory.get_item_instance_id_by_equipment_slot(est)
        if iid is None:
            continue
        agg = item_repository.find_by_id(iid)
        if agg is not None:
            counts[agg.item_spec.item_spec_id] += 1
    return dict(counts)


def remove_one_item_of_spec_from_inventory(
    inventory: PlayerInventoryAggregate,
    item_spec_id: ItemSpecId,
    item_repository: ItemRepository,
) -> bool:
    """指定仕様のアイテムを1つだけインベントリから除去（drop_item）。"""
    for i in range(inventory.max_slots):
        sid = SlotId(i)
        iid = inventory.get_item_instance_id_by_slot(sid)
        if iid is None:
            continue
        agg = item_repository.find_by_id(iid)
        if agg is not None and agg.item_spec.item_spec_id == item_spec_id:
            inventory.drop_item(sid)
            return True
    return False


def grant_item_specs_to_inventory(
    player_id: PlayerId,
    item_spec_ids: tuple[ItemSpecId, ...],
    item_repository: ItemRepository,
    item_spec_repository: ItemSpecRepository,
    player_inventory_repository: PlayerInventoryRepository,
) -> None:
    """各 ItemSpecId について新規 ItemAggregate を生成してインベントリに追加する。"""
    inv = player_inventory_repository.find_by_id(player_id)
    if inv is None:
        return
    for spec_id in item_spec_ids:
        spec_union = item_spec_repository.find_by_id(spec_id)
        if spec_union is None:
            continue
        spec = (
            spec_union.to_item_spec()
            if hasattr(spec_union, "to_item_spec")
            else spec_union
        )
        instance_id = item_repository.generate_item_instance_id()
        item_aggregate = ItemAggregate.create(
            item_instance_id=instance_id,
            item_spec=spec,
            quantity=1,
        )
        item_repository.save(item_aggregate)
        inv.acquire_item(instance_id, item_spec_id_value=spec.item_spec_id.value)
    player_inventory_repository.save(inv)
