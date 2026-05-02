from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import ISpotGraphRepository


class InMemorySpotGraphRepository(ISpotGraphRepository):
    """テスト・デモ用のインメモリスポットグラフリポジトリ。"""

    def __init__(self, graph: SpotGraphAggregate) -> None:
        self._graph = graph

    def find_graph(self) -> SpotGraphAggregate:
        return self._graph

    def save(self, graph: SpotGraphAggregate) -> None:
        self._graph = graph
