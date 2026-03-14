import logging
from typing import Callable, List, Set

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.time_of_day import (
    is_active_at_time,
    time_of_day_from_tick,
)


class WorldSimulationMonsterBehaviorStageService:
    """アクティブスポット上の actor behavior を処理する stage service。"""

    def __init__(
        self,
        monster_repository: MonsterRepository,
        world_time_config_service: WorldTimeConfigService,
        unit_of_work: UnitOfWork,
        logger: logging.Logger,
        actors_sorted_by_distance_to_players: Callable[
            [PhysicalMapAggregate], List[WorldObject]
        ],
        process_single_actor_behavior: Callable[
            [WorldObject, PhysicalMapAggregate, WorldTick], None
        ],
    ) -> None:
        self._monster_repository = monster_repository
        self._world_time_config_service = world_time_config_service
        self._unit_of_work = unit_of_work
        self._logger = logger
        self._actors_sorted_by_distance_to_players = actors_sorted_by_distance_to_players
        self._process_single_actor_behavior = process_single_actor_behavior

    def run(
        self,
        maps: List[PhysicalMapAggregate],
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
    ) -> None:
        for physical_map in maps:
            if physical_map.spot_id not in active_spot_ids:
                continue
            for actor in self._actors_sorted_by_distance_to_players(physical_map):
                if actor.is_busy(current_tick):
                    continue
                if not self._can_actor_act(actor, current_tick):
                    continue
                try:
                    self._process_single_actor_behavior(
                        actor,
                        physical_map,
                        current_tick,
                    )
                except DomainException as exc:
                    self._logger.warning(
                        "Behavior skipped for actor %s due to domain rule: %s",
                        actor.object_id,
                        str(exc),
                    )
                except ApplicationException:
                    raise
                except Exception as exc:
                    self._logger.error(
                        "Failed to update actor %s in map %s: %s",
                        actor.object_id,
                        physical_map.spot_id,
                        str(exc),
                        exc_info=True,
                    )

    def _can_actor_act(self, actor: WorldObject, current_tick: WorldTick) -> bool:
        if not isinstance(actor.component, AutonomousBehaviorComponent):
            return True

        ticks_per_day = self._world_time_config_service.get_ticks_per_day()
        time_of_day = time_of_day_from_tick(current_tick.value, ticks_per_day)
        if not is_active_at_time(actor.component.active_time, time_of_day):
            return False

        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if monster and monster.tick_hunger(current_tick):
            try:
                monster.starve(current_tick)
                self._monster_repository.save(monster)
                self._unit_of_work.process_sync_events()
            except DomainException as exc:
                self._logger.warning(
                    "Starvation skipped for actor %s: %s",
                    actor.object_id,
                    str(exc),
                )
            return False

        monster = self._monster_repository.find_by_world_object_id(actor.object_id)
        if monster and monster.die_from_old_age(current_tick):
            try:
                self._monster_repository.save(monster)
                self._unit_of_work.process_sync_events()
            except DomainException as exc:
                self._logger.warning(
                    "Old-age death skipped for actor %s: %s",
                    actor.object_id,
                    str(exc),
                )
            return False

        return True
