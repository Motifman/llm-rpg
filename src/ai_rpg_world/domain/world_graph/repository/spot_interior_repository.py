from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior


class ISpotInteriorRepository(ABC):
    """スポット内部構造の永続化"""

    @abstractmethod
    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotInterior]:
        ...

    @abstractmethod
    def save(self, spot_id: SpotId, interior: SpotInterior) -> None:
        ...
