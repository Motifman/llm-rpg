from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, FrozenSet, Optional, Tuple

from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world_graph.enum.spot_object_type import SpotObjectTypeEnum
from ai_rpg_world.domain.world_graph.value_object.interaction_def import InteractionDef
from ai_rpg_world.domain.world_graph.value_object.object_description_variant import (
    ObjectDescriptionVariant,
)
from ai_rpg_world.domain.world_graph.value_object.puzzle_state import PuzzleState
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
    puzzle: Optional[PuzzleState] = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("Spot object name cannot be empty")

    def with_state(self, new_state: Dict[str, Any]) -> SpotObject:
        return replace(self, state=dict(new_state))

    def with_visible(self, visible: bool) -> SpotObject:
        return replace(self, is_visible=visible)

    def with_puzzle(self, puzzle: Optional[PuzzleState]) -> SpotObject:
        return replace(self, puzzle=puzzle)

    def resolved_description(self, world_flags: FrozenSet[str]) -> str:
        for variant in self.description_variants:
            if variant.required_flag and variant.required_flag not in world_flags:
                continue
            if variant.required_state:
                if any(self.state.get(k) != v for k, v in variant.required_state.items()):
                    continue
            return variant.description
        return self.description
