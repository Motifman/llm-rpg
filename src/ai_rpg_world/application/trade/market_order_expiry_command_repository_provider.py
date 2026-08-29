"""期限切れ市場注文commandが同じtransactionで使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)


class MarketOrderExpiryCommandRepositoryProviderPort(Protocol):
    """預り品またはgoldの返却に必要なrepositoryだけを公開する。"""

    @property
    def player_inventories(self) -> PlayerInventoryRepository: ...

    @property
    def player_statuses(self) -> PlayerStatusRepository: ...

    @property
    def items(self) -> ItemRepository: ...


__all__ = ["MarketOrderExpiryCommandRepositoryProviderPort"]
