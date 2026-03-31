from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import SpotPresenceInvariantException
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


@dataclass(frozen=True)
class SpotPresence:
    """あるスポットに誰がいるか（不変）"""

    spot_id: SpotId
    present_entity_ids: FrozenSet[EntityId]

    def is_present(self, entity_id: EntityId) -> bool:
        return entity_id in self.present_entity_ids

    def count(self) -> int:
        return len(self.present_entity_ids)

    def add(self, entity_id: EntityId) -> SpotPresence:
        if entity_id in self.present_entity_ids:
            raise SpotPresenceInvariantException(
                f"Entity {entity_id} is already present at spot {self.spot_id}"
            )
        new_ids = set(self.present_entity_ids)
        new_ids.add(entity_id)
        return SpotPresence(self.spot_id, frozenset(new_ids))

    def remove(self, entity_id: EntityId) -> SpotPresence:
        if entity_id not in self.present_entity_ids:
            raise SpotPresenceInvariantException(
                f"Entity {entity_id} is not present at spot {self.spot_id}"
            )
        new_ids = set(self.present_entity_ids)
        new_ids.remove(entity_id)
        return SpotPresence(self.spot_id, frozenset(new_ids))

    @staticmethod
    def empty(spot_id: SpotId) -> SpotPresence:
        return SpotPresence(spot_id, frozenset())
