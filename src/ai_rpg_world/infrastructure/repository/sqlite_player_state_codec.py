"""Helpers for normalized player status / inventory persistence."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.agent_need import AgentNeed, NeedType
from ai_rpg_world.domain.player.value_object.agent_needs import AgentNeeds
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def build_player_inventory(
    *,
    row: sqlite3.Row,
    inventory_slot_rows: list[sqlite3.Row],
    equipment_slot_rows: list[sqlite3.Row],
    reserved_item_rows: list[sqlite3.Row],
) -> PlayerInventoryAggregate:
    inventory_slots = {
        SlotId(int(slot_row["slot_id"])): (
            None if slot_row["item_instance_id"] is None else ItemInstanceId(int(slot_row["item_instance_id"]))
        )
        for slot_row in inventory_slot_rows
    }
    equipment_slots = {
        EquipmentSlotType(str(slot_row["equipment_slot_type"])): (
            None if slot_row["item_instance_id"] is None else ItemInstanceId(int(slot_row["item_instance_id"]))
        )
        for slot_row in equipment_slot_rows
    }
    reserved = {ItemInstanceId(int(reserved_row["item_instance_id"])) for reserved_row in reserved_item_rows}
    return PlayerInventoryAggregate.restore_from_data(
        player_id=PlayerId(int(row["player_id"])),
        max_slots=int(row["max_slots"]),
        inventory_slots=inventory_slots,
        equipment_slots=equipment_slots,
        reserved_item_ids=reserved,
    )


def build_player_status(
    *,
    row: sqlite3.Row,
    active_effect_rows: list[sqlite3.Row],
    need_rows: list[sqlite3.Row] | None = None,
) -> PlayerStatusAggregate:
    exp_table = ExpTable(
        base_exp=float(row["exp_table_base_exp"]),
        exponent=float(row["exp_table_exponent"]),
        level_offset=float(row["exp_table_level_offset"]),
    )
    return PlayerStatusAggregate(
        player_id=PlayerId(int(row["player_id"])),
        base_stats=BaseStats(
            max_hp=int(row["base_max_hp"]),
            max_mp=int(row["base_max_mp"]),
            attack=int(row["base_attack"]),
            defense=int(row["base_defense"]),
            speed=int(row["base_speed"]),
            critical_rate=float(row["base_critical_rate"]),
            evasion_rate=float(row["base_evasion_rate"]),
        ),
        stat_growth_factor=StatGrowthFactor(
            hp_factor=float(row["growth_hp_factor"]),
            mp_factor=float(row["growth_mp_factor"]),
            attack_factor=float(row["growth_attack_factor"]),
            defense_factor=float(row["growth_defense_factor"]),
            speed_factor=float(row["growth_speed_factor"]),
            critical_rate_factor=float(row["growth_critical_rate_factor"]),
            evasion_rate_factor=float(row["growth_evasion_rate_factor"]),
        ),
        exp_table=exp_table,
        growth=Growth(
            level=int(row["growth_level"]),
            total_exp=int(row["growth_total_exp"]),
            exp_table=exp_table,
        ),
        gold=Gold(int(row["gold_value"])),
        hp=Hp.create(int(row["hp_value"]), int(row["hp_max"])),
        mp=Mp.create(int(row["mp_value"]), int(row["mp_max"])),
        stamina=Stamina.create(int(row["stamina_value"]), int(row["stamina_max"])),
        current_spot_id=None if row["current_spot_id"] is None else SpotId(int(row["current_spot_id"])),
        is_down=bool(row["is_down"]),
        active_effects=[
            StatusEffect(
                effect_type=StatusEffectType[str(effect_row["effect_type"])],
                value=float(effect_row["effect_value"]),
                expiry_tick=WorldTick(int(effect_row["expiry_tick"])),
            )
            for effect_row in active_effect_rows
        ],
        attention_level=AttentionLevel(str(row["attention_level"])),
        needs=_build_needs(need_rows or []),
        # Phase 4-D-2: state_json 列が存在し非 NULL なら JSON 復元、
        # それ以外 (旧 schema 由来 / NULL) は空 dict として扱う。
        state=_state_from_row(row),
    )


def _state_from_row(row: sqlite3.Row) -> dict[str, Any]:
    """row から state_json を読み出して dict に戻す。旧 schema との互換あり。"""
    try:
        keys = row.keys()
    except Exception:
        return {}
    if "state_json" not in keys:
        return {}
    raw = row["state_json"]
    if raw is None:
        return {}
    try:
        loaded = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _build_needs(need_rows: list[sqlite3.Row]) -> AgentNeeds:
    """SQLite の game_player_needs 行から AgentNeeds を復元する。"""
    if not need_rows:
        return AgentNeeds.default()
    needs = []
    for nr in need_rows:
        try:
            need_type = NeedType(str(nr["need_type"]))
            needs.append(AgentNeed.create(need_type, int(nr["value"]), int(nr["max_value"])))
        except (ValueError, KeyError):
            continue
    return AgentNeeds(tuple(needs)) if needs else AgentNeeds.default()


__all__ = ["build_player_inventory", "build_player_status"]
