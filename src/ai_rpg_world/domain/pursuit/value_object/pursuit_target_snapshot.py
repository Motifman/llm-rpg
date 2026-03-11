from dataclasses import dataclass

from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class PursuitTargetSnapshot:
    """追跡対象の現在スナップショット。"""

    target_id: WorldObjectId
    spot_id: SpotId
    coordinate: Coordinate
