"""アイテム受渡しcommandが同じtransaction内で使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)


class SpotGraphReadRepositoryPort(Protocol):
    """item transfer commandが位置とgraph idの参照にだけ使う契約。"""

    def find_graph(self) -> SpotGraphAggregate: ...


class ItemTransferCommandRepositoryProviderPort(Protocol):
    """give_itemが1 command内で必要とするrepositoryだけを公開する。"""

    @property
    def player_inventories(self) -> PlayerInventoryRepository: ...

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...

    @property
    def items(self) -> ItemRepository: ...

    @property
    def spot_graph(self) -> SpotGraphReadRepositoryPort: ...

    @property
    def spot_interiors(self) -> ISpotInteriorRepository: ...


__all__ = [
    "ItemTransferCommandRepositoryProviderPort",
    "SpotGraphReadRepositoryPort",
]
