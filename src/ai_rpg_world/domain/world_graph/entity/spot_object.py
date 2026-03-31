from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


@dataclass(frozen=True)
class SpotObject:
    object_id: SpotObjectId
    name: str
    description: str
    object_type: SpotObjectTypeEnum
    state: Dict[str, Any]
    interactions: Tuple[InteractionDef, ...]
    is_visible: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("Spot object name cannot be empty")

    def with_state(self, new_state: Dict[str, Any]) -> SpotObject:
        return SpotObject(
            object_id=self.object_id,
            name=self.name,
            description=self.description,
            object_type=self.object_type,
            state=dict(new_state),
            interactions=self.interactions,
            is_visible=self.is_visible,
        )

    def with_visible(self, visible: bool) -> SpotObject:
        return SpotObject(
            object_id=self.object_id,
            name=self.name,
            description=self.description,
            object_type=self.object_type,
            state=dict(self.state),
            interactions=self.interactions,
            is_visible=visible,
        )
