from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Optional, Tuple

from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


@dataclass(frozen=True)
class SpotObject:
    object_id: SpotObjectId
    name: str
    description: str
    object_type: SpotObjectTypeEnum
    state: Dict[str, Any]
    interactions: Tuple[InteractionDef, ...]
    description_variants: Tuple[ObjectDescriptionVariant, ...] = ()
    is_visible: bool = True
    trap: Optional[TrapDef] = None

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
            description_variants=self.description_variants,
            is_visible=self.is_visible,
            trap=self.trap,
        )

    def with_visible(self, visible: bool) -> SpotObject:
        return SpotObject(
            object_id=self.object_id,
            name=self.name,
            description=self.description,
            object_type=self.object_type,
            state=dict(self.state),
            interactions=self.interactions,
            description_variants=self.description_variants,
            is_visible=visible,
            trap=self.trap,
        )

    def resolved_description(self, world_flags: FrozenSet[str]) -> str:
        for variant in self.description_variants:
            if variant.required_flag and variant.required_flag not in world_flags:
                continue
            if variant.required_state:
                if any(self.state.get(k) != v for k, v in variant.required_state.items()):
                    continue
            return variant.description
        return self.description
