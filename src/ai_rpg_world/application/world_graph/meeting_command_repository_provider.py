"""会議開始commandがtransaction内で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)


class MeetingCommandRepositoryProviderPort(Protocol):
    """会議開始に必要なrepositoryだけをcommand中に公開する。"""

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...


__all__ = ["MeetingCommandRepositoryProviderPort"]
