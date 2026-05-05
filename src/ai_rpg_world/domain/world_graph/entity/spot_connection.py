from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    SpotConnectionValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.passage_condition import PassageCondition


@dataclass(frozen=True)
class SpotConnection:
    """スポット間の接続（有向エッジ）。

    `passage` を指定すると、`is_passable` と `sound_permeability` は
    `passage` から導出される（同期）。`passage=None` のレガシー接続は
    従来通り `is_passable` / `sound_permeability` を直接保持する。
    """

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
    passage: Optional[Passage] = None

    def __post_init__(self) -> None:
        if self.travel_ticks < 0:
            raise SpotConnectionValidationException(
                f"travel_ticks must be non-negative: {self.travel_ticks}"
            )
        if not (0.0 <= self.sound_permeability <= 1.0):
            raise SpotConnectionValidationException(
                f"sound_permeability must be between 0.0 and 1.0: {self.sound_permeability}"
            )
        if self.passage is not None:
            # passage がある場合は is_passable / sound_permeability を同期する。
            # frozen dataclass なので object.__setattr__ で上書き。
            object.__setattr__(self, "is_passable", self.passage.traversable)
            object.__setattr__(self, "sound_permeability", self.passage.sound_permeability)
