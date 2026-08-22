"""期限切れ取引提案commandが同じtransactionで使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)


class TradeOfferExpiryCommandRepositoryProviderPort(Protocol):
    """予約解除に必要なrepositoryだけを期限切れ処理へ公開する。"""

    @property
    def player_inventories(self) -> PlayerInventoryRepository: ...

    @property
    def items(self) -> ItemRepository: ...


__all__ = ["TradeOfferExpiryCommandRepositoryProviderPort"]
