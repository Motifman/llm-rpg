from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class PursuitLastKnownState:
    """追跡継続に使う対象の最後の既知状態。"""

    target_id: WorldObjectId
    spot_id: SpotId
    coordinate: Coordinate
    observed_at_tick: Optional[WorldTick] = None
