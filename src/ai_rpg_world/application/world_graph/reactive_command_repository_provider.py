"""reactive binding commandが同じ確定境界で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)


class ReactiveCommandRepositoryProviderPort(Protocol):
    """reactive object / passageが更新するrepositoryだけを公開する。"""

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...

    @property
    def spot_interiors(self) -> ISpotInteriorRepository: ...


__all__ = ["ReactiveCommandRepositoryProviderPort"]
