"""synchronized action commandが確定境界内で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)


class SynchronizedActionCommandRepositoryProviderPort(Protocol):
    """同期操作groupの解決に必要なrepositoryだけを公開する。"""

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...


__all__ = ["SynchronizedActionCommandRepositoryProviderPort"]
