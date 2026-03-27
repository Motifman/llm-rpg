"""Helpers for normalized player status / inventory persistence."""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


def build_player_inventory(*, row: object, inventory_slot_rows: list[object], equipment_slot_rows: list[object], reserved_item_rows: list[object]) -> PlayerInventoryAggregate:
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
    reserved = {
        ItemInstanceId(int(reserved_row["item_instance_id"]))
        for reserved_row in reserved_item_rows
    }
    return PlayerInventoryAggregate.restore_from_data(
        player_id=PlayerId(int(row["player_id"])),
        max_slots=int(row["max_slots"]),
        inventory_slots=inventory_slots,
        equipment_slots=equipment_slots,
        reserved_item_ids=reserved,
    )


def build_player_status(*, row: object, path_rows: list[object], active_effect_rows: list[object], pursuit_target_row: object | None, pursuit_last_known_row: object | None) -> PlayerStatusAggregate:
    exp_table = ExpTable(
        base_exp=float(row["exp_table_base_exp"]),
        exponent=float(row["exp_table_exponent"]),
        level_offset=float(row["exp_table_level_offset"]),
    )
    pursuit_state = PlayerPursuitState.empty()
    if pursuit_target_row is not None or pursuit_last_known_row is not None:
        target_snapshot = None
        if pursuit_target_row is not None:
            target_snapshot = PursuitTargetSnapshot(
                target_id=WorldObjectId(int(pursuit_target_row["target_id"])),
                spot_id=SpotId(int(pursuit_target_row["spot_id"])),
                coordinate=Coordinate(int(pursuit_target_row["x"]), int(pursuit_target_row["y"]), int(pursuit_target_row["z"])),
            )
        last_known = None
        if pursuit_last_known_row is not None:
            last_known = PursuitLastKnownState(
                target_id=WorldObjectId(int(pursuit_last_known_row["target_id"])),
                spot_id=SpotId(int(pursuit_last_known_row["spot_id"])),
                coordinate=Coordinate(int(pursuit_last_known_row["x"]), int(pursuit_last_known_row["y"]), int(pursuit_last_known_row["z"])),
                observed_at_tick=None if pursuit_last_known_row["observed_at_tick"] is None else WorldTick(int(pursuit_last_known_row["observed_at_tick"])),
            )
        target_id = target_snapshot.target_id if target_snapshot is not None else last_known.target_id
        pursuit_state = PlayerPursuitState.from_parts(
            pursuit=PursuitState(
                actor_id=WorldObjectId.create(int(row["player_id"])),
                target_id=target_id,
                target_snapshot=target_snapshot,
                last_known=last_known,
                failure_reason=None if row["pursuit_failure_reason"] is None else PursuitFailureReason[str(row["pursuit_failure_reason"])],
            )
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
        navigation_state=PlayerNavigationState.from_parts(
            current_spot_id=None if row["current_spot_id"] is None else SpotId(int(row["current_spot_id"])),
            current_coordinate=_coord_or_none(row["current_coordinate_x"], row["current_coordinate_y"], row["current_coordinate_z"]),
            current_destination=_coord_or_none(row["current_destination_x"], row["current_destination_y"], row["current_destination_z"]),
            planned_path=[Coordinate(int(path_row["x"]), int(path_row["y"]), int(path_row["z"])) for path_row in path_rows],
            goal_destination_type=row["goal_destination_type"],
            goal_spot_id=None if row["goal_spot_id"] is None else SpotId(int(row["goal_spot_id"])),
            goal_location_area_id=None if row["goal_location_area_id"] is None else LocationAreaId(int(row["goal_location_area_id"])),
            goal_world_object_id=None if row["goal_world_object_id"] is None else WorldObjectId(int(row["goal_world_object_id"])),
        ),
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
        pursuit_state=pursuit_state,
    )


def _coord_or_none(x: object, y: object, z: object) -> Coordinate | None:
    if x is None or y is None or z is None:
        return None
    return Coordinate(int(x), int(y), int(z))


__all__ = ["build_player_inventory", "build_player_status"]
