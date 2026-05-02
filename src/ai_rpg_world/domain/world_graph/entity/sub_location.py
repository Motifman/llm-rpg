from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


@dataclass(frozen=True)
class SubLocation:
    sub_location_id: SubLocationId
    name: str
    description: str
    accessible_object_ids: Tuple[SpotObjectId, ...]
    is_hidden: bool
    discovery_condition: Optional[DiscoveryCondition] = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("SubLocation name cannot be empty")

    def revealed(self) -> SubLocation:
        if not self.is_hidden:
            return self
        return SubLocation(
            sub_location_id=self.sub_location_id,
            name=self.name,
            description=self.description,
            accessible_object_ids=self.accessible_object_ids,
            is_hidden=False,
            discovery_condition=self.discovery_condition,
        )
