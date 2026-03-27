"""Helpers for normalized hit-box persistence."""

from __future__ import annotations

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_collision_policy import (
    ObstacleCollisionPolicy,
    TargetCollisionPolicy,
)
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_effect import HitEffect, HitEffectType
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def build_hit_box(
    *,
    row: object,
    shape_rows: list[object],
    effect_rows: list[object],
    hit_target_rows: list[int],
    obstacle_rows: list[object],
) -> HitBoxAggregate:
    aggregate = HitBoxAggregate(
        hit_box_id=HitBoxId(int(row["hit_box_id"])),
        spot_id=SpotId(int(row["spot_id"])),
        owner_id=WorldObjectId(int(row["owner_id"])),
        shape=HitBoxShape(
            [
                RelativeCoordinate(
                    dx=int(shape_row["dx"]),
                    dy=int(shape_row["dy"]),
                    dz=int(shape_row["dz"]),
                )
                for shape_row in shape_rows
            ]
        ),
        initial_coordinate=Coordinate(
            int(row["current_x"]),
            int(row["current_y"]),
            int(row["current_z"]),
        ),
        start_tick=WorldTick(int(row["start_tick"])),
        duration=int(row["duration"]),
        power_multiplier=float(row["power_multiplier"]),
        velocity=HitBoxVelocity(
            dx=float(row["velocity_dx"]),
            dy=float(row["velocity_dy"]),
            dz=float(row["velocity_dz"]),
        ),
        attacker_stats=(
            None
            if row["attacker_max_hp"] is None
            else BaseStats(
                max_hp=int(row["attacker_max_hp"]),
                max_mp=int(row["attacker_max_mp"]),
                attack=int(row["attacker_attack"]),
                defense=int(row["attacker_defense"]),
                speed=int(row["attacker_speed"]),
                critical_rate=float(row["attacker_critical_rate"]),
                evasion_rate=float(row["attacker_evasion_rate"]),
            )
        ),
        target_collision_policy=TargetCollisionPolicy(str(row["target_collision_policy"])),
        obstacle_collision_policy=ObstacleCollisionPolicy(str(row["obstacle_collision_policy"])),
        hit_effects=tuple(
            HitEffect(
                effect_type=HitEffectType(str(effect_row["effect_type"])),
                duration_ticks=int(effect_row["duration_ticks"]),
                intensity=float(effect_row["intensity"]),
                chance=float(effect_row["chance"]),
            )
            for effect_row in effect_rows
        ),
        movement_capability=MovementCapability(
            capabilities=frozenset(
                MovementCapabilityEnum(capability)
                for capability in str(row["movement_capabilities"]).split(",")
                if capability
            ),
            speed_modifier=float(row["movement_speed_modifier"]),
        ),
        activation_tick=int(row["activation_tick"]),
        skill_id=row["skill_id"],
    )
    aggregate._current_coordinate = Coordinate(
        int(row["current_x"]),
        int(row["current_y"]),
        int(row["current_z"]),
    )
    aggregate._previous_coordinate = Coordinate(
        int(row["previous_x"]),
        int(row["previous_y"]),
        int(row["previous_z"]),
    )
    aggregate._precise_x = float(row["precise_x"])
    aggregate._precise_y = float(row["precise_y"])
    aggregate._precise_z = float(row["precise_z"])
    aggregate._is_active = bool(row["is_active"])
    aggregate._hit_targets = {WorldObjectId(int(target_id)) for target_id in hit_target_rows}
    aggregate._hit_obstacle_coordinates = {
        Coordinate(int(obstacle_row["x"]), int(obstacle_row["y"]), int(obstacle_row["z"]))
        for obstacle_row in obstacle_rows
    }
    aggregate.clear_events()
    return aggregate


__all__ = ["build_hit_box"]
