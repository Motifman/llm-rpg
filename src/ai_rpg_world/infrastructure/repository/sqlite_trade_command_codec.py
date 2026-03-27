"""Trade コマンド用 SQLite 行とドメイン集約の変換（インフラ専用）。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
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
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_pursuit_state import PlayerPursuitState
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import PursuitFailureReason
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import PursuitLastKnownState
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import PursuitTargetSnapshot
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.trade.aggregate.trade_aggregate import TradeAggregate
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus, TradeType
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_state_codec import (
    item_spec_to_payload,
    payload_to_item_spec,
)


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


def item_aggregate_to_storage(item: ItemAggregate) -> Tuple[int, int, str]:
    inst = item.item_instance
    spec_dict = item_spec_to_payload(inst.item_spec)
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
    spec = payload_to_item_spec(body["spec"])
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


_PLAYER_STATUS_SCHEMA_VERSION = 1


def _require_mapping(raw: Any, label: str) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return raw


def _coord_to_list(c: Coordinate) -> List[int]:
    return [c.x, c.y, c.z]


def _list_to_coord(raw: Any) -> Coordinate:
    if not isinstance(raw, list) or len(raw) not in (2, 3):
        raise ValueError("coordinate must be [x,y] or [x,y,z]")
    x, y = int(raw[0]), int(raw[1])
    z = int(raw[2]) if len(raw) > 2 else 0
    return Coordinate(x, y, z)


def _optional_spot_id(raw: Any) -> Optional[SpotId]:
    if raw is None:
        return None
    return SpotId(int(raw))


def _optional_location_area_id(raw: Any) -> Optional[LocationAreaId]:
    if raw is None:
        return None
    return LocationAreaId(int(raw))


def _optional_world_object_id(raw: Any) -> Optional[WorldObjectId]:
    if raw is None:
        return None
    return WorldObjectId(int(raw))


def _navigation_state_to_dict(nav: PlayerNavigationState) -> Dict[str, Any]:
    return {
        "current_spot_id": int(nav.current_spot_id) if nav.current_spot_id is not None else None,
        "current_coordinate": _coord_to_list(nav.current_coordinate) if nav.current_coordinate else None,
        "current_destination": _coord_to_list(nav.current_destination) if nav.current_destination else None,
        "planned_path": [_coord_to_list(c) for c in nav.planned_path],
        "goal_destination_type": nav.goal_destination_type,
        "goal_spot_id": int(nav.goal_spot_id) if nav.goal_spot_id is not None else None,
        "goal_location_area_id": int(nav.goal_location_area_id) if nav.goal_location_area_id is not None else None,
        "goal_world_object_id": int(nav.goal_world_object_id) if nav.goal_world_object_id is not None else None,
    }


def _dict_to_navigation_state(data: Dict[str, Any]) -> PlayerNavigationState:
    path_raw = data.get("planned_path") or []
    if not isinstance(path_raw, list):
        raise ValueError("planned_path must be a list")
    path: Tuple[Coordinate, ...] = tuple(_list_to_coord(x) for x in path_raw)
    ccoord = data.get("current_coordinate")
    cdest = data.get("current_destination")
    return PlayerNavigationState.from_parts(
        current_spot_id=_optional_spot_id(data.get("current_spot_id")),
        current_coordinate=_list_to_coord(ccoord) if ccoord is not None else None,
        current_destination=_list_to_coord(cdest) if cdest is not None else None,
        planned_path=path,
        goal_destination_type=data.get("goal_destination_type"),
        goal_spot_id=_optional_spot_id(data.get("goal_spot_id")),
        goal_location_area_id=_optional_location_area_id(data.get("goal_location_area_id")),
        goal_world_object_id=_optional_world_object_id(data.get("goal_world_object_id")),
    )


def _status_effect_to_dict(effect: StatusEffect) -> Dict[str, Any]:
    return {
        "effect_type": effect.effect_type.name,
        "value": effect.value,
        "expiry_tick": effect.expiry_tick.value,
    }


def _dict_to_status_effect(data: Dict[str, Any]) -> StatusEffect:
    name = str(data["effect_type"])
    return StatusEffect(
        effect_type=StatusEffectType[name],
        value=float(data["value"]),
        expiry_tick=WorldTick(int(data["expiry_tick"])),
    )


def _pursuit_snapshot_to_dict(s: PursuitTargetSnapshot) -> Dict[str, Any]:
    return {
        "target_id": int(s.target_id),
        "spot_id": int(s.spot_id),
        "coordinate": _coord_to_list(s.coordinate),
    }


def _dict_to_pursuit_snapshot(data: Dict[str, Any]) -> PursuitTargetSnapshot:
    return PursuitTargetSnapshot(
        target_id=WorldObjectId(int(data["target_id"])),
        spot_id=SpotId(int(data["spot_id"])),
        coordinate=_list_to_coord(data["coordinate"]),
    )


def _last_known_to_dict(lk: PursuitLastKnownState) -> Dict[str, Any]:
    tick = lk.observed_at_tick.value if lk.observed_at_tick is not None else None
    return {
        "target_id": int(lk.target_id),
        "spot_id": int(lk.spot_id),
        "coordinate": _coord_to_list(lk.coordinate),
        "observed_at_tick": tick,
    }


def _dict_to_last_known(data: Dict[str, Any]) -> PursuitLastKnownState:
    tick_raw = data.get("observed_at_tick")
    tick: Optional[WorldTick] = WorldTick(int(tick_raw)) if tick_raw is not None else None
    return PursuitLastKnownState(
        target_id=WorldObjectId(int(data["target_id"])),
        spot_id=SpotId(int(data["spot_id"])),
        coordinate=_list_to_coord(data["coordinate"]),
        observed_at_tick=tick,
    )


def _pursuit_state_core_to_dict(p: PursuitState) -> Dict[str, Any]:
    ts = p.target_snapshot
    lk = p.last_known
    fr = p.failure_reason
    return {
        "actor_id": int(p.actor_id),
        "target_id": int(p.target_id),
        "target_snapshot": _pursuit_snapshot_to_dict(ts) if ts is not None else None,
        "last_known": _last_known_to_dict(lk) if lk is not None else None,
        "failure_reason": fr.name if fr is not None else None,
    }


def _dict_to_pursuit_state_core(data: Dict[str, Any]) -> PursuitState:
    fr_raw = data.get("failure_reason")
    failure_reason = PursuitFailureReason[str(fr_raw)] if fr_raw is not None else None
    ts_raw = data.get("target_snapshot")
    lk_raw = data.get("last_known")
    return PursuitState(
        actor_id=WorldObjectId(int(data["actor_id"])),
        target_id=WorldObjectId(int(data["target_id"])),
        target_snapshot=(
            _dict_to_pursuit_snapshot(_require_mapping(ts_raw, "target_snapshot"))
            if ts_raw is not None
            else None
        ),
        last_known=(
            _dict_to_last_known(_require_mapping(lk_raw, "last_known"))
            if lk_raw is not None
            else None
        ),
        failure_reason=failure_reason,
    )


def player_status_to_json_bytes(status: PlayerStatusAggregate) -> bytes:
    """PlayerStatusAggregate を UTF-8 JSON バイト列に変換（schema_version 付き）。"""
    exp_table = status.exp_table
    growth = status.growth
    body: Dict[str, Any] = {
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
        "navigation_state": _navigation_state_to_dict(status._navigation_state),
        "is_down": status.is_down,
        "active_effects": [_status_effect_to_dict(e) for e in status._active_effects],
        "attention_level": status.attention_level.value,
        "pursuit": (
            None
            if status._pursuit_state.pursuit is None
            else _pursuit_state_core_to_dict(status._pursuit_state.pursuit)
        ),
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
    active_effects = [
        _dict_to_status_effect(_require_mapping(x, "active_effects[]")) for x in effects_raw
    ]

    pursuit_raw = data.get("pursuit")
    if pursuit_raw is None:
        pursuit_vo = PlayerPursuitState.empty()
    elif isinstance(pursuit_raw, dict):
        pursuit_vo = PlayerPursuitState.from_parts(pursuit=_dict_to_pursuit_state_core(pursuit_raw))
    else:
        raise ValueError("pursuit must be a JSON object or null")

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
        navigation_state=_dict_to_navigation_state(_require_mapping(data["navigation_state"], "navigation_state")),
        is_down=bool(data["is_down"]),
        active_effects=active_effects,
        attention_level=AttentionLevel(str(data["attention_level"])),
        pursuit_state=pursuit_vo,
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
