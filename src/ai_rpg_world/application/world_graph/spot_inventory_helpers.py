from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, FrozenSet, Mapping, Optional

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.scenario.scenario_loader import InitialItemSpec

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.value_object.inventory_item_appearance import (
    InventoryItemAppearance,
)
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


def inventory_item_appearances(
    inventory: PlayerInventoryAggregate,
    item_repository: ItemRepository,
) -> dict[ItemInstanceId, InventoryItemAppearance]:
    """occupied slots の ItemInstanceId から、探索用の見た目写像を作る。"""
    appearances: dict[ItemInstanceId, InventoryItemAppearance] = {}
    for _slot_id, iid in inventory.iter_occupied_slots():
        item = item_repository.find_by_id(iid)
        if item is None:
            continue
        appearances[iid] = InventoryItemAppearance(
            item_spec_id=item.item_spec.item_spec_id,
            is_spoiled=bool(item.state.get("spoiled")),
        )
    return appearances


def count_owned_item_instances_by_spec(
    inventory: PlayerInventoryAggregate,
    item_repository: ItemRepository,
) -> Mapping[ItemSpecId, int]:
    """「消費可能な」アイテム instance を ItemSpecId 別に重複保持数で数える。

    HAS_ITEM precondition の数量チェック、REMOVE_ITEM の複数消費判定で
    利用する。`remove_one_item_of_spec_from_inventory` と semantics を
    揃えるため、装備スロットは含めない（装備中の剣は「消費可能」では
    ないので、required_quantity チェックの分母にしない）。
    `collect_owned_item_spec_ids_from_inventory` が装備込みの「所持
    set」を返すのとは意図的に意味が異なる。

    instance.quantity（同一 instance 内の stack 数）は加算しない。
    1 instance = 1 個として数える Phase 2-A の方針に従う。
    """
    counts: Counter[ItemSpecId] = Counter()
    seen_item_instance_ids: set[ItemInstanceId] = set()
    for i in range(inventory.max_slots):
        sid = SlotId(i)
        iid = inventory.get_item_instance_id_by_slot(sid)
        if iid is None:
            continue
        if iid in seen_item_instance_ids:
            continue
        seen_item_instance_ids.add(iid)
        if inventory.is_item_reserved(iid):
            continue
        agg = item_repository.find_by_id(iid)
        if agg is not None:
            counts[agg.item_spec.item_spec_id] += 1
    return dict(counts)


ItemRemovalPlan = tuple[tuple[SlotId, ItemInstanceId], ...]


def plan_item_removals_from_inventory(
    inventory: PlayerInventoryAggregate,
    item_spec_ids: tuple[ItemSpecId, ...],
    item_repository: ItemRepository,
) -> Optional[ItemRemovalPlan]:
    """予約されていない具体instanceを、所持品を変更せず必要数ぶん確保する。"""
    remaining: Counter[ItemSpecId] = Counter(item_spec_ids)
    planned: list[tuple[SlotId, ItemInstanceId]] = []
    seen_item_instance_ids: set[ItemInstanceId] = set()
    for slot_id, item_instance_id in inventory.iter_occupied_slots():
        if not remaining:
            break
        if inventory.is_item_reserved(item_instance_id):
            continue
        if item_instance_id in seen_item_instance_ids:
            continue
        seen_item_instance_ids.add(item_instance_id)
        item = item_repository.find_by_id(item_instance_id)
        if item is None:
            continue
        item_spec_id = item.item_spec.item_spec_id
        if remaining[item_spec_id] <= 0:
            continue
        planned.append((slot_id, item_instance_id))
        remaining[item_spec_id] -= 1
        if remaining[item_spec_id] == 0:
            del remaining[item_spec_id]
    return tuple(planned) if not remaining else None


def apply_item_removal_plan(
    inventory: PlayerInventoryAggregate,
    plan: ItemRemovalPlan,
) -> bool:
    """事前計画が現在も有効なら、全対象を一括でインベントリから外す。"""
    slot_ids = tuple(slot_id for slot_id, _item_instance_id in plan)
    item_instance_ids = tuple(
        item_instance_id for _slot_id, item_instance_id in plan
    )
    if len(set(slot_ids)) != len(slot_ids):
        return False
    if len(set(item_instance_ids)) != len(item_instance_ids):
        return False
    for slot_id, expected_item_instance_id in plan:
        current = inventory.get_item_instance_id_by_slot(slot_id)
        if current != expected_item_instance_id:
            return False
        if inventory.is_item_reserved(expected_item_instance_id):
            return False
    for slot_id, _item_instance_id in plan:
        inventory.drop_item(slot_id)
    return True


def remove_items_of_specs_from_inventory(
    inventory: PlayerInventoryAggregate,
    item_spec_ids: tuple[ItemSpecId, ...],
    item_repository: ItemRepository,
) -> bool:
    """指定品目を全量確保できる場合だけ、予約品を避けてまとめて除去する。"""
    plan = plan_item_removals_from_inventory(
        inventory, item_spec_ids, item_repository
    )
    if plan is None:
        return False
    return apply_item_removal_plan(inventory, plan)


def remove_one_item_of_spec_from_inventory(
    inventory: PlayerInventoryAggregate,
    item_spec_id: ItemSpecId,
    item_repository: ItemRepository,
) -> bool:
    """指定仕様の未予約アイテムを1つだけインベントリから除去する。"""
    return remove_items_of_specs_from_inventory(
        inventory, (item_spec_id,), item_repository
    )


def grant_item_specs_to_inventory(
    player_id: PlayerId,
    item_spec_ids: tuple[ItemSpecId, ...],
    item_repository: ItemRepository,
    item_spec_repository: ItemSpecRepository,
    player_inventory_repository: PlayerInventoryRepository,
) -> None:
    """各 ItemSpecId について新規 ItemAggregate を生成してインベントリに追加する。

    state を持たないシンプルな付与専用の旧 API。effect 駆動の `GIVE_ITEM` 等で
    使われ続ける。シナリオ初期化で initial state を仕込みたい場合は
    `grant_initial_items_to_inventory` を使う (Phase 4-D)。
    """
    inv = player_inventory_repository.find_by_id(player_id)
    if inv is None:
        return
    for spec_id in item_spec_ids:
        _create_and_acquire(
            spec_id=spec_id,
            state=None,
            inventory=inv,
            item_repository=item_repository,
            item_spec_repository=item_spec_repository,
        )
    player_inventory_repository.save(inv)


def grant_initial_items_to_inventory(
    player_id: PlayerId,
    initial_items: "tuple[InitialItemSpec, ...]",
    item_repository: ItemRepository,
    item_spec_repository: ItemSpecRepository,
    player_inventory_repository: PlayerInventoryRepository,
) -> None:
    """シナリオ起動時のプレイヤー初期所持品を生成してインベントリに追加する。

    各 `InitialItemSpec` (spec_id + state) ごとに新規 `ItemAggregate` を作り、
    state を持つ場合は `ItemAggregate.create(state=...)` 経由で初期 state を
    仕込んだ instance を生成する。effect 経由で生まれる instance (`GIVE_ITEM`)
    とは別経路で、Phase 4-A 以降の per-instance state を JSON だけで初期化
    できるようにするための helper。
    """
    inv = player_inventory_repository.find_by_id(player_id)
    if inv is None:
        return
    for initial in initial_items:
        # 空 dict と非空 dict を区別する必要は無い (どちらでも domain 側で
        # 同じ「state を持たない instance」になる)。常に dict コピーを渡し、
        # `if state else None` の falsy 判定で意味が変わる罠を避ける。
        _create_and_acquire(
            spec_id=initial.spec_id,
            state=dict(initial.state),
            inventory=inv,
            item_repository=item_repository,
            item_spec_repository=item_spec_repository,
        )
    player_inventory_repository.save(inv)


def _create_and_acquire(
    *,
    spec_id: ItemSpecId,
    state: Optional[Mapping[str, Any]],
    inventory: PlayerInventoryAggregate,
    item_repository: ItemRepository,
    item_spec_repository: ItemSpecRepository,
) -> None:
    """`ItemAggregate` を生成して inventory に acquire させる内部 helper。"""
    spec_union = item_spec_repository.find_by_id(spec_id)
    if spec_union is None:
        return
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
        state=state,
    )
    item_repository.save(item_aggregate)
    inventory.acquire_item(instance_id, item_spec_id_value=spec.item_spec_id.value)
