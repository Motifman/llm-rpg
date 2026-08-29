"""monster behavior commandが同じ確定境界で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)


class MonsterBehaviorCommandRepositoryProviderPort(Protocol):
    """monster 1体の行動に必要なwrite repositoryだけを公開する。"""

    @property
    def monsters(self) -> MonsterRepository: ...

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...

    @property
    def spot_interiors(self) -> ISpotInteriorRepository: ...

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...


__all__ = ["MonsterBehaviorCommandRepositoryProviderPort"]
