from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.entity.sub_location import SubLocation
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import UnknownSpotObjectException
from ai_rpg_world.domain.world_graph.value_object.discoverable_item import DiscoverableItem
from ai_rpg_world.domain.world_graph.value_object.ground_item import GroundItem
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


@dataclass(frozen=True)
class SpotInterior:
    sub_locations: Tuple[SubLocation, ...]
    objects: Tuple[SpotObject, ...]
    ground_items: Tuple[GroundItem, ...]
    discoverable_items: Tuple[DiscoverableItem, ...]

    @staticmethod
    def empty() -> SpotInterior:
        return SpotInterior((), (), (), ())

    def get_object(self, object_id: SpotObjectId) -> Optional[SpotObject]:
        for o in self.objects:
            if o.object_id == object_id:
                return o
        return None

    def replace_object(self, obj: SpotObject) -> SpotInterior:
        if not any(o.object_id == obj.object_id for o in self.objects):
            raise UnknownSpotObjectException(str(obj.object_id))
        new_objs = tuple(o if o.object_id != obj.object_id else obj for o in self.objects)
        return SpotInterior(
            sub_locations=self.sub_locations,
            objects=new_objs,
            ground_items=self.ground_items,
            discoverable_items=self.discoverable_items,
        )

    def replace_sub_location(self, sub: SubLocation) -> SpotInterior:
        if not any(s.sub_location_id == sub.sub_location_id for s in self.sub_locations):
            raise ValueError(f"SubLocation not in interior: {sub.sub_location_id}")
        new_subs = tuple(
            s if s.sub_location_id != sub.sub_location_id else sub for s in self.sub_locations
        )
        return SpotInterior(
            sub_locations=new_subs,
            objects=self.objects,
            ground_items=self.ground_items,
            discoverable_items=self.discoverable_items,
        )

    def replace_discoverable_items(self, items: Tuple[DiscoverableItem, ...]) -> SpotInterior:
        return SpotInterior(
            sub_locations=self.sub_locations,
            objects=self.objects,
            ground_items=self.ground_items,
            discoverable_items=items,
        )
