"""取引commandが同じtransaction内で使うrepository束の契約。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.trade.repository.trade_repository import TradeRepository


class TradeCommandRepositoryProviderPort(Protocol):
    """取引commandに必要な5つのrepositoryだけを公開する。"""

    @property
    def trades(self) -> TradeRepository:
        """取引集約repositoryを返す。"""
        ...

    @property
    def player_inventories(self) -> PlayerInventoryRepository:
        """所持品集約repositoryを返す。"""
        ...

    @property
    def player_statuses(self) -> PlayerStatusRepository:
        """プレイヤー状態集約repositoryを返す。"""
        ...

    @property
    def player_profiles(self) -> PlayerProfileRepository:
        """プレイヤープロフィールrepositoryを返す。"""
        ...

    @property
    def items(self) -> ItemRepository:
        """アイテム集約repositoryを返す。"""
        ...


__all__ = ["TradeCommandRepositoryProviderPort"]
