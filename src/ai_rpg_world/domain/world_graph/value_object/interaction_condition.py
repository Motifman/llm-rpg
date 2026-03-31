from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

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
