from typing import Callable, List, Set

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class WorldSimulationHitBoxStageService:
    """HitBox 更新と保存を担当する stage service。"""

    def __init__(
        self,
        physical_map_repository: PhysicalMapRepository,
        update_hit_boxes: Callable[[PhysicalMapAggregate, WorldTick], None],
    ) -> None:
        self._physical_map_repository = physical_map_repository
        self._update_hit_boxes = update_hit_boxes

    def run(
        self,
        maps: List[PhysicalMapAggregate],
        active_spot_ids: Set[SpotId],
        current_tick: WorldTick,
    ) -> None:
        for physical_map in maps:
            if physical_map.spot_id not in active_spot_ids:
                continue

            latest_map = self._physical_map_repository.find_by_spot_id(physical_map.spot_id)
            if latest_map is not None:
                physical_map = latest_map

            self._update_hit_boxes(physical_map, current_tick)
            self._physical_map_repository.save(physical_map)
