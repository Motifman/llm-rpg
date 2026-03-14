import logging
from typing import List, Optional, Set

from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
    MonsterTemplateRepository,
)
from ai_rpg_world.domain.monster.repository.spawn_table_repository import SpawnTableRepository
from ai_rpg_world.domain.monster.value_object.spawn_slot import SpawnSlot
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay


class MonsterSpawnSlotService:
    """spawn slot と legacy respawn を扱う service。"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        monster_repository: MonsterRepository,
        skill_loadout_repository: SkillLoadoutRepository,
        spawn_table_repository: SpawnTableRepository | None,
        monster_template_repository: MonsterTemplateRepository | None,
        unit_of_work: UnitOfWork,
        logger: logging.Logger,
    ) -> None:
        self._physical_map_repository = physical_map_repository
        self._monster_repository = monster_repository
        self._skill_loadout_repository = skill_loadout_repository
        self._spawn_table_repository = spawn_table_repository
        self._monster_template_repository = monster_template_repository
        self._unit_of_work = unit_of_work
        self._logger = logger

    def process_spawn_and_respawn_by_slots(
        self,
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
        time_of_day: TimeOfDay,
    ) -> None:
        if self._spawn_table_repository is None or self._monster_template_repository is None:
            return

        for spot_id in active_spot_ids:
            table = self._spawn_table_repository.find_by_spot_id(spot_id)
            if not table:
                continue
            physical_map = self._physical_map_repository.find_by_spot_id(spot_id)
            weather_type = (
                physical_map.weather_state.weather_type
                if physical_map and physical_map.weather_state
                else None
            )
            area_traits = physical_map.area_traits if physical_map else None
            monsters_for_spot = self._monster_repository.find_by_spot_id(spot_id)
            for slot in table.slots:
                if slot.condition is not None and not slot.condition.is_satisfied(
                    time_of_day,
                    weather_type=weather_type,
                    area_traits=area_traits,
                ):
                    continue
                monster_for_slot = self._find_monster_for_slot(slot, monsters_for_spot)
                count_alive = self._count_alive_for_slot(slot, monsters_for_spot)
                if count_alive >= slot.max_concurrent:
                    continue
                if monster_for_slot is not None:
                    self._respawn_existing_slot_monster(
                        monster_for_slot,
                        slot,
                        current_tick,
                    )
                    continue
                self._spawn_new_monster_for_slot(slot, current_tick)

    def process_respawn_legacy(
        self,
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
        time_of_day: TimeOfDay,
    ) -> None:
        for monster in self._monster_repository.find_all():
            if monster.status != MonsterStatusEnum.DEAD:
                continue
            if monster.spot_id is None or monster.spot_id not in active_spot_ids:
                continue
            if not monster.should_respawn(current_tick):
                continue
            condition = monster.template.respawn_info.condition
            if condition is not None and not condition.is_satisfied_at(time_of_day):
                continue
            respawn_coord = monster.get_respawn_coordinate()
            if respawn_coord is None:
                continue
            try:
                monster.respawn(respawn_coord, current_tick, monster.spot_id)
                self._monster_repository.save(monster)
            except DomainException as exc:
                self._logger.warning(
                    "Respawn skipped for monster %s: %s",
                    monster.monster_id,
                    str(exc),
                )

    def _respawn_existing_slot_monster(
        self,
        monster_for_slot: MonsterAggregate,
        slot: SpawnSlot,
        current_tick: WorldTick,
    ) -> None:
        if (
            monster_for_slot.status != MonsterStatusEnum.DEAD
            or not monster_for_slot.should_respawn(current_tick)
        ):
            return
        try:
            monster_for_slot.respawn(slot.coordinate, current_tick, slot.spot_id)
            self._monster_repository.save(monster_for_slot)
            self._unit_of_work.process_sync_events()
        except DomainException as exc:
            self._logger.warning(
                "Respawn skipped for slot %s %s: %s",
                slot.spot_id,
                slot.coordinate,
                str(exc),
            )

    def _spawn_new_monster_for_slot(
        self,
        slot: SpawnSlot,
        current_tick: WorldTick,
    ) -> None:
        if self._monster_template_repository is None:
            return

        template = self._monster_template_repository.find_by_id(slot.template_id)
        if not template:
            return
        try:
            monster_id = self._monster_repository.generate_monster_id()
            world_object_id = self._monster_repository.generate_world_object_id_for_npc()
            loadout = SkillLoadoutAggregate.create(
                SkillLoadoutId(world_object_id.value),
                world_object_id.value,
                10,
                10,
            )
            monster = MonsterAggregate.create(
                monster_id,
                template,
                world_object_id,
                skill_loadout=loadout,
            )
            monster.spawn(slot.coordinate, slot.spot_id, current_tick)
            self._monster_repository.save(monster)
            self._skill_loadout_repository.save(loadout)
            self._unit_of_work.process_sync_events()
        except DomainException as exc:
            self._logger.warning(
                "Spawn skipped for slot %s %s: %s",
                slot.spot_id,
                slot.coordinate,
                str(exc),
            )

    @staticmethod
    def _find_monster_for_slot(
        slot: SpawnSlot,
        monsters: List[MonsterAggregate],
    ) -> Optional[MonsterAggregate]:
        for monster in monsters:
            respawn_coord = monster.get_respawn_coordinate()
            if (
                respawn_coord is not None
                and monster.spot_id == slot.spot_id
                and respawn_coord == slot.coordinate
                and monster.template.template_id == slot.template_id
            ):
                return monster
        return None

    @staticmethod
    def _count_alive_for_slot(
        slot: SpawnSlot,
        monsters: List[MonsterAggregate],
    ) -> int:
        return sum(
            1
            for monster in monsters
            if monster.status == MonsterStatusEnum.ALIVE
            and monster.spot_id == slot.spot_id
            and monster.get_respawn_coordinate() == slot.coordinate
            and monster.template.template_id == slot.template_id
        )
