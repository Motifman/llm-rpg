from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any, FrozenSet, Mapping, Optional

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.scenario.scenario_loader import InitialItemSpec

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
    for i in range(inventory.max_slots):
        sid = SlotId(i)
        iid = inventory.get_item_instance_id_by_slot(sid)
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
