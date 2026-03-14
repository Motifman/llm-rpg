from typing import Callable, List, Set

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.world_time_config_service import (
    WorldTimeConfigService,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay, time_of_day_from_tick


class WorldSimulationMonsterLifecycleStageService:
    """スポーン・リスポーン・飢餓移住を束ねる stage service。"""

    def __init__(
        self,
        world_time_config_service: WorldTimeConfigService,
        has_spawn_slot_support: Callable[[], bool],
        has_hunger_migration_support: Callable[[], bool],
        process_spawn_and_respawn_by_slots: Callable[
            [Set[SpotId], WorldTick, TimeOfDay], None
        ],
        process_respawn_legacy: Callable[[Set[SpotId], WorldTick, TimeOfDay], None],
        process_hunger_migration_for_spot: Callable[
            [PhysicalMapAggregate, WorldTick, Set[SpotId]], None
        ],
    ) -> None:
        self._world_time_config_service = world_time_config_service
        self._has_spawn_slot_support = has_spawn_slot_support
        self._has_hunger_migration_support = has_hunger_migration_support
        self._process_spawn_and_respawn_by_slots = process_spawn_and_respawn_by_slots
        self._process_respawn_legacy = process_respawn_legacy
        self._process_hunger_migration_for_spot = process_hunger_migration_for_spot

    def run(
        self,
        maps: List[PhysicalMapAggregate],
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
    ) -> None:
        ticks_per_day = self._world_time_config_service.get_ticks_per_day()
        time_of_day = time_of_day_from_tick(current_tick.value, ticks_per_day)

        if self._has_spawn_slot_support():
            self._process_spawn_and_respawn_by_slots(
                active_spot_ids=active_spot_ids,
                current_tick=current_tick,
                time_of_day=time_of_day,
            )
        else:
            self._process_respawn_legacy(active_spot_ids, current_tick, time_of_day)

        if not self._has_hunger_migration_support():
            return

        for physical_map in maps:
            if physical_map.spot_id not in active_spot_ids:
                continue
            self._process_hunger_migration_for_spot(
                physical_map,
                current_tick,
                active_spot_ids,
            )
