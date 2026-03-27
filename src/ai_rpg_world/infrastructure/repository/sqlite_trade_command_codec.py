"""Trade コマンド用 SQLite 行とドメイン集約の変換（インフラ専用）。"""
from __future__ import annotations

import json
import pickle
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.enum.player_enum import ControlType, Element, Race, Role
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus, TradeType
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope


def trade_aggregate_to_row(trade: TradeAggregate) -> Tuple[Any, ...]:
    scope = trade.trade_scope
    target = scope.target_player_id.value if scope.target_player_id is not None else None
    buyer = trade.buyer_id.value if trade.buyer_id is not None else None
    return (
        int(trade.trade_id),
        int(trade.seller_id),
        int(trade.offered_item_id),
        int(trade.requested_gold.value),
        trade.created_at.isoformat(),
        scope.trade_type.value,
        target,
        trade.status.value,
        int(trade.version),
        buyer,
    )


def row_to_trade_aggregate(row: Any) -> TradeAggregate:
    trade_type = TradeType(str(row["trade_type"]))
    target_raw = row["target_player_id"]
    if trade_type == TradeType.DIRECT:
        scope = TradeScope.direct_trade(PlayerId(int(target_raw)))
    else:
        scope = TradeScope.global_trade()
    buyer_raw = row["buyer_id"]
    buyer = PlayerId(int(buyer_raw)) if buyer_raw is not None else None
    return TradeAggregate(
        trade_id=TradeId(int(row["trade_id"])),
        seller_id=PlayerId(int(row["seller_id"])),
        offered_item_id=ItemInstanceId(int(row["offered_item_id"])),
        requested_gold=TradeRequestedGold.of(int(row["requested_gold"])),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        trade_scope=scope,
        status=TradeStatus(str(row["status"])),
        version=int(row["version"]),
        buyer_id=buyer,
    )


def profile_to_row(profile: PlayerProfileAggregate) -> Tuple[Any, ...]:
    return (
        int(profile.player_id),
        profile.name.value,
        profile.role.value,
        profile.race.value,
        profile.element.value,
        profile.control_type.value,
    )


def row_to_profile(row: Any) -> PlayerProfileAggregate:
    return PlayerProfileAggregate(
        player_id=PlayerId(int(row["player_id"])),
        name=PlayerName(str(row["name"])),
        role=Role(str(row["role"])),
        race=Race(str(row["race"])),
        element=Element(str(row["element"])),
        control_type=ControlType(str(row["control_type"])),
    )


def _item_spec_to_dict(spec: ItemSpec) -> Dict[str, Any]:
    if spec.consume_effect is not None:
        raise ValueError(
            "game_items の JSON コーデックは consume_effect 付き ItemSpec をまだサポートしません"
        )
    return {
        "item_spec_id": int(spec.item_spec_id),
        "name": spec.name,
        "item_type": spec.item_type.value,
        "rarity": spec.rarity.value,
        "description": spec.description,
        "max_stack_size": int(spec.max_stack_size.value),
        "durability_max": spec.durability_max,
        "equipment_type": spec.equipment_type.value if spec.equipment_type else None,
        "is_placeable": spec.is_placeable,
        "placeable_object_type": spec.placeable_object_type,
    }


def _dict_to_item_spec(data: Dict[str, Any]) -> ItemSpec:
    eq_raw = data.get("equipment_type")
    equipment_type = EquipmentType(eq_raw) if eq_raw else None
    return ItemSpec(
        item_spec_id=ItemSpecId(int(data["item_spec_id"])),
        name=str(data["name"]),
        item_type=ItemType(str(data["item_type"])),
        rarity=Rarity(str(data["rarity"])),
        description=str(data["description"]),
        max_stack_size=MaxStackSize(int(data["max_stack_size"])),
        durability_max=data.get("durability_max"),
        equipment_type=equipment_type,
        is_placeable=bool(data.get("is_placeable", False)),
        placeable_object_type=data.get("placeable_object_type"),
        consume_effect=None,
    )


def item_aggregate_to_storage(item: ItemAggregate) -> Tuple[int, int, str]:
    inst = item.item_instance
    spec_dict = _item_spec_to_dict(inst.item_spec)
    dur = inst.durability
    body: Dict[str, Any] = {
        "quantity": int(inst.quantity),
        "durability": (
            None
            if dur is None
            else {"current": int(dur.current), "max": int(dur.max_value)}
        ),
        "spec": spec_dict,
    }
    return int(inst.item_instance_id), int(inst.item_spec.item_spec_id), json.dumps(body)


def storage_to_item_aggregate(item_instance_id: int, item_spec_id: int, payload_json: str) -> ItemAggregate:
    body = json.loads(payload_json)
    spec = _dict_to_item_spec(body["spec"])
    if int(spec.item_spec_id) != int(item_spec_id):
        raise ValueError("item_spec_id column と payload 内 spec が不一致")
    dur_data = body.get("durability")
    durability: Optional[Durability] = None
    if dur_data is not None:
        durability = Durability(max_value=int(dur_data["max"]), current=int(dur_data["current"]))
    instance = ItemInstance(
        item_instance_id=ItemInstanceId(int(item_instance_id)),
        item_spec=spec,
        durability=durability,
        quantity=int(body.get("quantity", 1)),
    )
    return ItemAggregate.create_from_instance(instance)


def inventory_to_json(inv: PlayerInventoryAggregate) -> str:
    inv_map: Dict[str, Optional[int]] = {}
    for i in range(inv.max_slots):
        sid = SlotId(i)
        iid = inv.get_item_instance_id_by_slot(sid)
        inv_map[str(i)] = iid.value if iid is not None else None
    eq_map: Dict[str, Optional[int]] = {}
    for et in EquipmentSlotType:
        iid = inv.get_item_instance_id_by_equipment_slot(et)
        eq_map[et.value] = iid.value if iid is not None else None
    payload = {
        "max_slots": inv.max_slots,
        "inventory": inv_map,
        "equipment": eq_map,
        "reserved": sorted(x.value for x in inv.reserved_item_ids),
    }
    return json.dumps(payload)


def json_to_inventory(player_id: int, payload_json: str) -> PlayerInventoryAggregate:
    data = json.loads(payload_json)
    max_slots = int(data["max_slots"])
    inv_slots: Dict[SlotId, Optional[ItemInstanceId]] = {}
    for k, v in data["inventory"].items():
        inv_slots[SlotId(int(k))] = ItemInstanceId(int(v)) if v is not None else None
    eq_slots: Dict[EquipmentSlotType, Optional[ItemInstanceId]] = {}
    for k, v in data["equipment"].items():
        eq_slots[EquipmentSlotType(str(k))] = ItemInstanceId(int(v)) if v is not None else None
    reserved: Set[ItemInstanceId] = {ItemInstanceId(int(x)) for x in data["reserved"]}
    return PlayerInventoryAggregate.restore_from_data(
        player_id=PlayerId(player_id),
        max_slots=max_slots,
        inventory_slots=inv_slots,
        equipment_slots=eq_slots,
        reserved_item_ids=reserved,
    )


def pickle_player_status(status: PlayerStatusAggregate) -> bytes:
    return pickle.dumps(status, protocol=pickle.HIGHEST_PROTOCOL)


def unpickle_player_status(blob: bytes) -> PlayerStatusAggregate:
    obj = pickle.loads(blob)
    if not isinstance(obj, PlayerStatusAggregate):
        raise TypeError("expected PlayerStatusAggregate blob")
    return obj


__all__ = [
    "inventory_to_json",
    "item_aggregate_to_storage",
    "json_to_inventory",
    "pickle_player_status",
    "profile_to_row",
    "row_to_profile",
    "row_to_trade_aggregate",
    "storage_to_item_aggregate",
    "trade_aggregate_to_row",
    "unpickle_player_status",
]
