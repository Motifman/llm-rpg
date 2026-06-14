"""World snapshot subsystem codec 群 (Phase 9-2 以降)。

各 subsystem は ``WorldSubsystemCodec`` を継承し、独立した
``capture`` / ``restore`` を提供する。

Phase 9-2 (= tier 1a 前半):
- ``WorldTickSubsystemCodec`` — world tick (= 続行 tick)
- ``PlayerPositionSubsystemCodec`` — 各 player の current_spot_id
- ``PlayerVitalsSubsystemCodec`` — 各 player の hp / mp / stamina / gold
- ``PlayerNeedsSubsystemCodec`` — 各 player の AgentNeeds (hunger 等)

Phase 9-2b (= tier 1a 後半):
- ``PlayerInventorySubsystemCodec`` — inventory / equipment slots + reserved
- ``PlayerGrowthSubsystemCodec`` — base_stats / growth_factor / exp_table / growth
- ``PlayerStateDictSubsystemCodec`` — scenario-defined ``_state`` dict

Phase 9-2c 候補 (= 必要になったら):
- ``_active_effects`` / ``_attention_level`` / ``_pursuit_state`` /
  ``_spot_navigation_state`` (= combat / nav sub-state)

Phase 9-3 以降:
- spot_interior / world_flags / scenario_event_progress / weather / travel
  / monster / quest 系
"""

from ai_rpg_world.application.being.world_subsystems.player_growth_codec import (
    PlayerGrowthSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_inventory_codec import (
    PlayerInventorySubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_needs_codec import (
    PlayerNeedsSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_position_codec import (
    PlayerPositionSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_state_dict_codec import (
    PlayerStateDictSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.player_vitals_codec import (
    PlayerVitalsSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.world_tick_codec import (
    WorldTickSubsystemCodec,
)

__all__ = [
    # Phase 9-2
    "WorldTickSubsystemCodec",
    "PlayerPositionSubsystemCodec",
    "PlayerVitalsSubsystemCodec",
    "PlayerNeedsSubsystemCodec",
    # Phase 9-2b
    "PlayerInventorySubsystemCodec",
    "PlayerGrowthSubsystemCodec",
    "PlayerStateDictSubsystemCodec",
]
