from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate


class ISpotGraphRepository(ABC):
    """スポットグラフ集約の永続化"""

    @abstractmethod
    def find_graph(self) -> SpotGraphAggregate:
        ...

    @abstractmethod
    def save(self, graph: SpotGraphAggregate) -> None:
        ...
