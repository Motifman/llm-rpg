from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import InteractionConditionTypeEnum
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


@dataclass(frozen=True)
class InteractionCondition:
    condition_type: InteractionConditionTypeEnum
    target_item_spec_id: Optional[ItemSpecId] = None
    target_object_id: Optional[SpotObjectId] = None
    required_state: Optional[Dict[str, Any]] = None
    flag_name: Optional[str] = None
    failure_message: str = ""
    # 脱出ゲーム拡張
    required_player_count: Optional[int] = None
    prepared_action_id: Optional[str] = None
    puzzle_input_key: Optional[str] = None
    required_item_spec_ids: Optional[Tuple[ItemSpecId, ...]] = None
