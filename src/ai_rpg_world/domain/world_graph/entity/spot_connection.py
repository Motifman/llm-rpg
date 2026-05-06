from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

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

    通行可否と音透過率は `passage` （Passage 値オブジェクト）から決まる。
    `passage` は接続の構造的な状態（壁/扉/開口/障壁）と現在の状態文字列を
    保持し、そこから traversable と sound_permeability が定まる。

    通行可否を読みたいコードは `conn.passage.traversable`、
    音透過率は `conn.passage.sound_permeability` を直接参照すること。
    """

    connection_id: ConnectionId
    from_spot_id: SpotId
    to_spot_id: SpotId
    name: str
    description: str
    travel_ticks: int
    is_bidirectional: bool
    passage_conditions: List[PassageCondition] = field(default_factory=list)
    passage: Passage = field(default_factory=Passage.open)

    def __post_init__(self) -> None:
        if self.travel_ticks < 0:
            raise SpotConnectionValidationException(
                f"travel_ticks must be non-negative: {self.travel_ticks}"
            )
