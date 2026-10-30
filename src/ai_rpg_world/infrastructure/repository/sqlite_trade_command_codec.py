"""Trade コマンド用 SQLite 行とドメイン集約の変換（インフラ専用）。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel, ControlType, Element, Race, Role
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus, TradeType
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_state_codec import (
    item_spec_to_payload,
    payload_to_item_spec,
)


def trade_aggregate_to_row(trade: TradeAggregate) -> tuple[Any, ...]:
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


def profile_to_row(profile: PlayerProfileAggregate) -> tuple[Any, ...]:
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


def item_aggregate_to_storage(item: ItemAggregate) -> tuple[int, int, str]:
    inst = item.item_instance
    spec_dict = item_spec_to_payload(inst.item_spec)
    dur = inst.durability
    body: dict[str, Any] = {
        "quantity": int(inst.quantity),
        "durability": (None if dur is None else {"current": int(dur.current), "max": int(dur.max_value)}),
        "spec": spec_dict,
    }
    return int(inst.item_instance_id), int(inst.item_spec.item_spec_id), json.dumps(body)


def storage_to_item_aggregate(item_instance_id: int, item_spec_id: int, payload_json: str) -> ItemAggregate:
    body = json.loads(payload_json)
    spec = payload_to_item_spec(body["spec"])
    if int(spec.item_spec_id) != int(item_spec_id):
        raise ValueError("item_spec_id column と payload 内 spec が不一致")
    dur_data = body.get("durability")
    durability: Durability | None = None
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
    inv_map: dict[str, int | None] = {}
    for i in range(inv.max_slots):
        sid = SlotId(i)
        iid = inv.get_item_instance_id_by_slot(sid)
        inv_map[str(i)] = iid.value if iid is not None else None
    eq_map: dict[str, int | None] = {}
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
    inv_slots: dict[SlotId, ItemInstanceId | None] = {}
    for k, v in data["inventory"].items():
        inv_slots[SlotId(int(k))] = ItemInstanceId(int(v)) if v is not None else None
    eq_slots: dict[EquipmentSlotType, ItemInstanceId | None] = {}
    for k, v in data["equipment"].items():
        eq_slots[EquipmentSlotType(str(k))] = ItemInstanceId(int(v)) if v is not None else None
    reserved: set[ItemInstanceId] = {ItemInstanceId(int(x)) for x in data["reserved"]}
    return PlayerInventoryAggregate.restore_from_data(
        player_id=PlayerId(player_id),
        max_slots=max_slots,
        inventory_slots=inv_slots,
        equipment_slots=eq_slots,
        reserved_item_ids=reserved,
    )


_PLAYER_STATUS_SCHEMA_VERSION = 1


def _require_mapping(raw: Any, label: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return raw


def _optional_spot_id(raw: Any) -> SpotId | None:
    if raw is None:
        return None
    return SpotId(int(raw))


def _status_effect_to_dict(effect: StatusEffect) -> dict[str, Any]:
    return {
        "effect_type": effect.effect_type.name,
        "value": effect.value,
        "expiry_tick": effect.expiry_tick.value,
    }


def _dict_to_status_effect(data: dict[str, Any]) -> StatusEffect:
    name = str(data["effect_type"])
    return StatusEffect(
        effect_type=StatusEffectType[name],
        value=float(data["value"]),
        expiry_tick=WorldTick(int(data["expiry_tick"])),
    )


def player_status_to_json_bytes(status: PlayerStatusAggregate) -> bytes:
    """PlayerStatusAggregate を UTF-8 JSON バイト列に変換（schema_version 付き）。"""
    exp_table = status.exp_table
    growth = status.growth
    body: dict[str, Any] = {
        "schema_version": _PLAYER_STATUS_SCHEMA_VERSION,
        "player_id": int(status.player_id),
        "base_stats": {
            "max_hp": status.base_stats.max_hp,
            "max_mp": status.base_stats.max_mp,
            "attack": status.base_stats.attack,
            "defense": status.base_stats.defense,
            "speed": status.base_stats.speed,
            "critical_rate": status.base_stats.critical_rate,
            "evasion_rate": status.base_stats.evasion_rate,
        },
        "stat_growth_factor": {
            "hp_factor": status.stat_growth_factor.hp_factor,
            "mp_factor": status.stat_growth_factor.mp_factor,
            "attack_factor": status.stat_growth_factor.attack_factor,
            "defense_factor": status.stat_growth_factor.defense_factor,
            "speed_factor": status.stat_growth_factor.speed_factor,
            "critical_rate_factor": status.stat_growth_factor.critical_rate_factor,
            "evasion_rate_factor": status.stat_growth_factor.evasion_rate_factor,
        },
        "exp_table": {
            "base_exp": exp_table.base_exp,
            "exponent": exp_table.exponent,
            "level_offset": exp_table.level_offset,
        },
        "growth": {
            "level": growth.level,
            "total_exp": growth.total_exp,
        },
        "gold": {"value": status.gold.value},
        "hp": {"value": status.hp.value, "max_hp": status.hp.max_hp},
        "mp": {"value": status.mp.value, "max_mp": status.mp.max_mp},
        "stamina": {"value": status.stamina.value, "max_stamina": status.stamina.max_stamina},
        "current_spot_id": int(status.current_spot_id) if status.current_spot_id is not None else None,
        "is_down": status.is_down,
        "active_effects": [_status_effect_to_dict(e) for e in status._active_effects],
        "attention_level": status.attention_level.value,
    }
    text = json.dumps(body, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return text.encode("utf-8")


def json_bytes_to_player_status(blob: bytes) -> PlayerStatusAggregate:
    """UTF-8 JSON バイト列から PlayerStatusAggregate を復元する。"""
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("player status payload must be UTF-8 JSON") from exc
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("player status root must be a JSON object")
    version = data.get("schema_version")
    if version != _PLAYER_STATUS_SCHEMA_VERSION:
        raise ValueError(f"unsupported player status schema_version: {version!r}")

    exp_data = data["exp_table"]
    exp_table = ExpTable(
        base_exp=float(exp_data["base_exp"]),
        exponent=float(exp_data["exponent"]),
        level_offset=float(exp_data.get("level_offset", 0.0)),
    )
    growth_data = data["growth"]
    growth = Growth(
        level=int(growth_data["level"]),
        total_exp=int(growth_data["total_exp"]),
        exp_table=exp_table,
    )
    bs = data["base_stats"]
    base_stats = BaseStats(
        max_hp=int(bs["max_hp"]),
        max_mp=int(bs["max_mp"]),
        attack=int(bs["attack"]),
        defense=int(bs["defense"]),
        speed=int(bs["speed"]),
        critical_rate=float(bs["critical_rate"]),
        evasion_rate=float(bs["evasion_rate"]),
    )
    sg = data["stat_growth_factor"]
    stat_growth_factor = StatGrowthFactor(
        hp_factor=float(sg["hp_factor"]),
        mp_factor=float(sg["mp_factor"]),
        attack_factor=float(sg["attack_factor"]),
        defense_factor=float(sg["defense_factor"]),
        speed_factor=float(sg["speed_factor"]),
        critical_rate_factor=float(sg["critical_rate_factor"]),
        evasion_rate_factor=float(sg["evasion_rate_factor"]),
    )
    hp_d = data["hp"]
    mp_d = data["mp"]
    st_d = data["stamina"]
    gold_d = data["gold"]
    effects_raw = data.get("active_effects") or []
    if not isinstance(effects_raw, list):
        raise ValueError("active_effects must be a list")
    active_effects = [_dict_to_status_effect(_require_mapping(x, "active_effects[]")) for x in effects_raw]

    return PlayerStatusAggregate(
        player_id=PlayerId(int(data["player_id"])),
        base_stats=base_stats,
        stat_growth_factor=stat_growth_factor,
        exp_table=exp_table,
        growth=growth,
        gold=Gold(int(gold_d["value"])),
        hp=Hp.create(int(hp_d["value"]), int(hp_d["max_hp"])),
        mp=Mp.create(int(mp_d["value"]), int(mp_d["max_mp"])),
        stamina=Stamina.create(int(st_d["value"]), int(st_d["max_stamina"])),
        current_spot_id=_optional_spot_id(
            data["current_spot_id"] if "current_spot_id" in data else data["navigation_state"].get("current_spot_id")
        ),
        is_down=bool(data["is_down"]),
        active_effects=active_effects,
        attention_level=AttentionLevel(str(data["attention_level"])),
    )


__all__ = [
    "inventory_to_json",
    "item_aggregate_to_storage",
    "json_bytes_to_player_status",
    "json_to_inventory",
    "player_status_to_json_bytes",
    "profile_to_row",
    "row_to_profile",
    "row_to_trade_aggregate",
    "storage_to_item_aggregate",
    "trade_aggregate_to_row",
]
