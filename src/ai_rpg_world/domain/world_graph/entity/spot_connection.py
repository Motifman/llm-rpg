from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition


@dataclass(frozen=True)
class SpotConnection:
    """スポット間の接続（有向エッジ）"""

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    name: str
    description: str
    travel_ticks: int
    is_bidirectional: bool
    passage_conditions: List[PassageCondition] = field(default_factory=list)
    sound_permeability: float = 1.0
    is_passable: bool = True

    def __post_init__(self) -> None:
        if self.travel_ticks < 0:
            raise ValueError("travel_ticks must be non-negative")
        if not (0.0 <= self.sound_permeability <= 1.0):
            raise ValueError("sound_permeability must be between 0.0 and 1.0")
