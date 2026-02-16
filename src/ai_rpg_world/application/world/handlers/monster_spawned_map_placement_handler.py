import logging
from typing import Union

from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.application.monster.exceptions import (
    MonsterNotFoundException,
    MapNotFoundForMonsterSkillException,
)
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.monster.event.monster_events import MonsterSpawnedEvent, MonsterRespawnedEvent
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.skill.constants import MAX_SKILL_SLOTS
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
    MonsterSkillInfo,
)
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


def _build_available_skills(monster) -> list:
    """モンスターのスキルロードアウトから MonsterSkillInfo のリストを組み立てる"""
    skills = []
    loadout = monster.skill_loadout
    deck = loadout.get_current_deck(0)
    for slot_index in range(MAX_SKILL_SLOTS):
        spec = deck.get_skill(slot_index)
        if spec is not None:
            skills.append(
                MonsterSkillInfo(
                    slot_index=slot_index,
                    range=spec.targeting_range,
                    mp_cost=spec.mp_cost or 0,
                )
            )
    return skills


def _coordinate_from_event_dict(d: dict) -> Coordinate:
    return Coordinate(
        d["x"],
        d["y"],
        d.get("z", 0),
    )


class MonsterSpawnedMapPlacementHandler(
    EventHandler[Union[MonsterSpawnedEvent, MonsterRespawnedEvent]]
):
    """MonsterSpawnedEvent / MonsterRespawnedEvent を受けてマップに WorldObject を配置するハンドラ"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        physical_map_repository: PhysicalMapRepository,
        unit_of_work: UnitOfWork,
    ):
        self._monster_repository = monster_repository
        self._physical_map_repository = physical_map_repository
        self._unit_of_work = unit_of_work
        self._logger = logging.getLogger(self.__class__.__name__)

    def handle(
        self,
        event: Union[MonsterSpawnedEvent, MonsterRespawnedEvent],
    ) -> None:
        try:
            self._handle_impl(event)
        except (ApplicationException, DomainException):
            raise
        except Exception as e:
            self._logger.exception(
                "Unexpected error in MonsterSpawnedMapPlacementHandler: %s", e
            )
            raise SystemErrorException(
                f"Monster spawned map placement failed: {e}",
                original_exception=e,
            ) from e

    def _handle_impl(
        self,
        event: Union[MonsterSpawnedEvent, MonsterRespawnedEvent],
    ) -> None:
        monster = self._monster_repository.find_by_id(event.aggregate_id)
        if not monster:
            raise MonsterNotFoundException(event.aggregate_id.value)

        physical_map = self._physical_map_repository.find_by_spot_id(event.spot_id)
        if not physical_map:
            raise MapNotFoundForMonsterSkillException(event.spot_id.value)

        coordinate = _coordinate_from_event_dict(event.coordinate)
        template = monster.template
        available_skills = _build_available_skills(monster)

        component = AutonomousBehaviorComponent(
            vision_range=template.vision_range,
            flee_threshold=template.flee_threshold,
            available_skills=available_skills,
            hp_percentage=1.0,
            race=template.race.value,
            faction=template.faction.value,
            behavior_strategy_type=template.behavior_strategy_type,
            phase_thresholds=list(template.phase_thresholds),
            pack_id=monster.pack_id,
            is_pack_leader=monster.is_pack_leader,
            ecology_type=template.ecology_type,
            ambush_chase_range=template.ambush_chase_range,
            territory_radius=template.territory_radius,
            active_time=template.active_time,
            threat_races=set(template.threat_races) if template.threat_races else None,
            prey_races=set(template.prey_races) if template.prey_races else None,
            hunger=0.0,
            hunger_increase_per_tick=template.hunger_increase_per_tick,
            hunger_starvation_threshold=template.hunger_starvation_threshold,
            starvation_ticks=template.starvation_ticks,
        )

        world_object = WorldObject(
            object_id=monster.world_object_id,
            coordinate=coordinate,
            object_type=ObjectTypeEnum.NPC,
            component=component,
        )

        physical_map.add_object(world_object)
        self._physical_map_repository.save(physical_map)
