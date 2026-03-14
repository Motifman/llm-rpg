import logging
from typing import Callable, List, Set

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.common.value_object import WorldTick
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
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

from ai_rpg_world.application.world.services.monster_behavior_coordinator import (
    MonsterBehaviorCoordinator,
)


class WorldSimulationMonsterBehaviorStageService:
    """アクティブスポット上の actor behavior を処理する stage service。"""

    def __init__(
        self,
        world_time_config_service: WorldTimeConfigService,
        logger: logging.Logger,
        actors_sorted_by_distance_to_players: Callable[
            [PhysicalMapAggregate], List[WorldObject]
        ],
        behavior_coordinator: MonsterBehaviorCoordinator,
    ) -> None:
        self._world_time_config_service = world_time_config_service
        self._logger = logger
        self._actors_sorted_by_distance_to_players = actors_sorted_by_distance_to_players
        self._behavior_coordinator = behavior_coordinator

    def run(
        self,
        maps: List[PhysicalMapAggregate],
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
        skipped_actor_ids: Set[WorldObjectId] | None = None,
    ) -> None:
        skipped = skipped_actor_ids or set()
        for physical_map in maps:
            if physical_map.spot_id not in active_spot_ids:
                continue
            for actor in self._actors_sorted_by_distance_to_players(physical_map):
                if actor.object_id in skipped:
                    continue
                if actor.is_busy(current_tick):
                    continue
                if not self._can_actor_act(actor, current_tick):
                    continue
                try:
                    self._behavior_coordinator.process_actor_behavior(
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
        return is_active_at_time(actor.component.active_time, time_of_day)
