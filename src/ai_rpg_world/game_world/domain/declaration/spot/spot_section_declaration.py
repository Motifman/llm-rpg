from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.spot_declaration_exception import DuplicateReachableObjectException
from ai_rpg_world.game_world.domain.value_object import Capacity, DisplayName, ObjectId, SpotId, SpotSectionId


@final
@dataclass(frozen=True)
class NoCapacity:
    pass


@final
@dataclass(frozen=True)
class SpotSectionDeclaration:
    section_id: SpotSectionId
    spot_id: SpotId
    name: DisplayName
    capacity: Capacity | NoCapacity
    reachable_objects: tuple[ObjectId, ...]

    def __post_init__(self) -> None:
        if len(set(self.reachable_objects)) != len(self.reachable_objects):
            raise DuplicateReachableObjectException(
                f"SpotSectionDeclaration {self.section_id.value} lists a reachable object more than once"
            )
