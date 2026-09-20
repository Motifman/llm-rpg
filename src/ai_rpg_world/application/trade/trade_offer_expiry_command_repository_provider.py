"""期限切れ取引提案commandが同じtransactionで使うrepository束。"""

from typing import Protocol

from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.trade.aggregate.pending_trade_offer import PendingTradeOffer
from ai_rpg_world.domain.trade.value_object.trade_offer_id import TradeOfferId


class PendingTradeOfferExpiryStorePort(Protocol):
    """期限切れ処理が確定区間内で使う提案storeの最小契約。"""

    def expired_offers(self, current_tick: int) -> tuple[PendingTradeOffer, ...]: ...

    def find(self, offer_id: TradeOfferId) -> PendingTradeOffer | None: ...

    def put(self, offer: PendingTradeOffer) -> None: ...


class TradeOfferExpiryCommandRepositoryProviderPort(Protocol):
    """予約解除に必要なrepositoryだけを期限切れ処理へ公開する。"""

    @property
    def player_inventories(self) -> PlayerInventoryRepository: ...

    @property
    def items(self) -> ItemRepository: ...

    @property
    def pending_trade_offers(self) -> PendingTradeOfferExpiryStorePort: ...


__all__ = [
    "PendingTradeOfferExpiryStorePort",
    "TradeOfferExpiryCommandRepositoryProviderPort",
]
