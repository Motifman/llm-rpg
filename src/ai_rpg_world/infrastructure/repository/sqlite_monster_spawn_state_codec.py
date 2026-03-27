"""Helpers for normalized spawn table persistence."""

from __future__ import annotations

from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import SpotTraitEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


def build_spawn_slot(
    *,
    spot_id: int,
    row: object,
    preferred_weather_rows: list[str],
    required_trait_rows: list[str],
) -> SpawnSlot:
    condition = None
    if row["time_band"] is not None or preferred_weather_rows or required_trait_rows:
        condition = SpawnCondition(
            time_band=None if row["time_band"] is None else TimeOfDay(row["time_band"]),
            preferred_weather=(
                None
                if not preferred_weather_rows
                else frozenset(WeatherTypeEnum(value) for value in preferred_weather_rows)
            ),
            required_area_traits=(
                None
                if not required_trait_rows
                else frozenset(SpotTraitEnum(value) for value in required_trait_rows)
            ),
        )
    return SpawnSlot(
        spot_id=SpotId(spot_id),
        coordinate=Coordinate(int(row["x"]), int(row["y"]), int(row["z"])),
        template_id=MonsterTemplateId(int(row["template_id"])),
        weight=int(row["weight"]),
        condition=condition,
        max_concurrent=int(row["max_concurrent"]),
    )


def build_spawn_table(spot_id: int, slots: list[SpawnSlot]) -> SpotSpawnTable:
    return SpotSpawnTable(spot_id=SpotId(spot_id), slots=slots)

