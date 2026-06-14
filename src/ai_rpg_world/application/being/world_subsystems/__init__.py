"""World snapshot subsystem codec 群 (Phase 9-2 以降)。

各 subsystem は ``WorldSubsystemCodec`` を継承し、独立した
``capture`` / ``restore`` を提供する。

Phase 9-2 の対象:
- ``WorldTickSubsystemCodec`` — world tick (= 続行 tick)
- ``PlayerPositionSubsystemCodec`` — 各 player の current_spot_id
- ``PlayerVitalsSubsystemCodec`` — 各 player の hp / mp / stamina / gold
- ``PlayerNeedsSubsystemCodec`` — 各 player の AgentNeeds (hunger 等)

Phase 9-2b 以降で追加予定:
- player inventory
- active_effects / growth / base_stats 等の full PlayerStatusAggregate
- spot interior / world flags / etc.
"""

from ai_rpg_world.application.being.world_subsystems.player_needs_codec import (
    PlayerNeedsSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_position_codec import (
    PlayerPositionSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_vitals_codec import (
    PlayerVitalsSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.world_tick_codec import (
    WorldTickSubsystemCodec,
)

__all__ = [
    "WorldTickSubsystemCodec",
    "PlayerPositionSubsystemCodec",
    "PlayerVitalsSubsystemCodec",
    "PlayerNeedsSubsystemCodec",
]
