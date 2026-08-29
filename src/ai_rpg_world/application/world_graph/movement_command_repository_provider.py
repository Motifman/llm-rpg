"""SpotGraph移動commandがtransaction内で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)


class MovementCommandRepositoryProviderPort(Protocol):
    """移動の開始・進行・中断に必要なrepositoryだけを公開する。"""

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...


__all__ = ["MovementCommandRepositoryProviderPort"]
