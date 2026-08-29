"""CommandScope内だけ使えるSpotGraph読み取り専用adapter。"""

from collections.abc import Callable

from ai_rpg_world.application.world_graph.item_transfer_command_repository_provider import (
    SpotGraphReadRepositoryPort,
)
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)


class ScopeBoundSpotGraphReadRepository:
    """find_graphだけを公開し、scope終了後の利用と書込み能力を遮断する。"""

    def __init__(
        self,
        repository: SpotGraphReadRepositoryPort,
        require_active: Callable[[], None],
    ) -> None:
        self._repository = repository
        self._require_active = require_active

    def find_graph(self) -> SpotGraphAggregate:
        self._require_active()
        return self._repository.find_graph()


__all__ = ["ScopeBoundSpotGraphReadRepository"]
