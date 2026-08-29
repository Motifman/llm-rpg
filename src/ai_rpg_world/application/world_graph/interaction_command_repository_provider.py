"""interactionが1 command内で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
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


class InteractionCommandRepositoryProviderPort(Protocol):
    """interactionに必要なrepositoryだけをcommand中に公開する。"""

    @property
    def spot_graph(self) -> ISpotGraphRepository: ...

    @property
    def spot_interiors(self) -> ISpotInteriorRepository: ...

    @property
    def player_inventories(self) -> PlayerInventoryRepository: ...

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...

    @property
    def items(self) -> ItemRepository: ...

    @property
    def item_specs(self) -> ItemSpecRepository: ...


__all__ = ["InteractionCommandRepositoryProviderPort"]
