"""Helpers for normalized monster template persistence."""

from __future__ import annotations

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.monster.enum.monster_enum import (
    ActiveTimeType,
    EcologyTypeEnum,
    MonsterFactionEnum,
)
from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.player.enum.player_enum import Race
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.enum.world_enum import SpotTraitEnum
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


def build_monster_template(
    *,
    row: object,
    skill_ids: list[int],
    phase_thresholds: list[float],
    threat_races: list[str],
    prey_races: list[str],
    growth_stage_rows: list[object],
    preferred_feed_item_spec_ids: list[int],
    respawn_preferred_weather: list[str],
    respawn_required_area_traits: list[str],
) -> MonsterTemplate:
    respawn_condition = None
    if row["respawn_time_band"] is not None or respawn_preferred_weather or respawn_required_area_traits:
        respawn_condition = SpawnCondition(
            time_band=None if row["respawn_time_band"] is None else TimeOfDay(row["respawn_time_band"]),
            preferred_weather=(
                None
                if not respawn_preferred_weather
                else frozenset(WeatherTypeEnum(value) for value in respawn_preferred_weather)
            ),
            required_area_traits=(
                None
                if not respawn_required_area_traits
                else frozenset(SpotTraitEnum(value) for value in respawn_required_area_traits)
            ),
        )
    return MonsterTemplate(
        template_id=MonsterTemplateId(int(row["template_id"])),
        name=row["name"],
        base_stats=BaseStats(
            max_hp=int(row["base_max_hp"]),
            max_mp=int(row["base_max_mp"]),
            attack=int(row["base_attack"]),
            defense=int(row["base_defense"]),
            speed=int(row["base_speed"]),
            critical_rate=float(row["base_critical_rate"]),
            evasion_rate=float(row["base_evasion_rate"]),
        ),
        reward_info=RewardInfo(
            exp=int(row["reward_exp"]),
            gold=int(row["reward_gold"]),
            loot_table_id=None if row["reward_loot_table_id"] is None else LootTableId(int(row["reward_loot_table_id"])),
        ),
        respawn_info=RespawnInfo(
            respawn_interval_ticks=int(row["respawn_interval_ticks"]),
            is_auto_respawn=bool(row["respawn_is_auto"]),
            condition=respawn_condition,
        ),
        race=Race(row["race"]),
        faction=MonsterFactionEnum(row["faction"]),
        description=row["description"],
        skill_ids=[SkillId(skill_id) for skill_id in skill_ids],
        vision_range=int(row["vision_range"]),
        flee_threshold=float(row["flee_threshold"]),
        behavior_strategy_type=row["behavior_strategy_type"],
        phase_thresholds=phase_thresholds,
        ecology_type=EcologyTypeEnum(row["ecology_type"]),
        ambush_chase_range=row["ambush_chase_range"],
        territory_radius=row["territory_radius"],
        active_time=ActiveTimeType(row["active_time"]),
        threat_races=frozenset(threat_races),
        prey_races=frozenset(prey_races),
        growth_stages=[
            GrowthStage(
                after_ticks=int(stage_row["after_ticks"]),
                stats_multiplier=float(stage_row["stats_multiplier"]),
                flee_bias_multiplier=(
                    None
                    if stage_row["flee_bias_multiplier"] is None
                    else float(stage_row["flee_bias_multiplier"])
                ),
                allow_chase=bool(stage_row["allow_chase"]),
            )
            for stage_row in growth_stage_rows
        ],
        hunger_increase_per_tick=float(row["hunger_increase_per_tick"]),
        hunger_decrease_on_prey_kill=float(row["hunger_decrease_on_prey_kill"]),
        hunger_starvation_threshold=float(row["hunger_starvation_threshold"]),
        starvation_ticks=int(row["starvation_ticks"]),
        max_age_ticks=row["max_age_ticks"],
        forage_threshold=float(row["forage_threshold"]),
        hunger_decrease_on_feed=float(row["hunger_decrease_on_feed"]),
        preferred_feed_item_spec_ids=frozenset(
            ItemSpecId(item_spec_id) for item_spec_id in preferred_feed_item_spec_ids
        ),
    )

