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

Phase 9-3 (= tier 1b 前半):
- ``WorldFlagsSubsystemCodec`` — scenario flag 集合
- ``ScenarioEventProgressSubsystemCodec`` — 発火済 / scheduled event_id
- ``SpotExplorationProgressSubsystemCodec`` — (player, spot) → 探索回数

Phase 9-3b (= tier 1b 後半、戦略 C = selective dynamic-only):
- ``SpotInteriorSubsystemCodec`` — sub_locations.is_hidden / objects.state /
  is_visible / puzzle / detail_read_by / ground_items / discoverable_items.is_discovered
- ``ItemInstanceSubsystemCodec`` — ItemInstance.quantity / durability.current / state

Phase 9-4 候補:
- combat sub-state (``_active_effects`` / ``_pursuit_state`` /
  ``_spot_navigation_state`` / ``_attention_level``)
- weather / day_night / travel stage
- sliding_window / observation_buffer / action_result
"""

from ai_rpg_world.application.being.world_subsystems.exploration_progress_codec import (
    SpotExplorationProgressSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.item_instance_codec import (
    ItemInstanceSubsystemCodec,
)
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
from ai_rpg_world.application.being.world_subsystems.scenario_event_progress_codec import (
    ScenarioEventProgressSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.spot_interior_codec import (
    SpotInteriorSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems.world_flags_codec import (
    WorldFlagsSubsystemCodec,
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
    # Phase 9-3
    "WorldFlagsSubsystemCodec",
    "ScenarioEventProgressSubsystemCodec",
    "SpotExplorationProgressSubsystemCodec",
    # Phase 9-3b
    "SpotInteriorSubsystemCodec",
    "ItemInstanceSubsystemCodec",
]
