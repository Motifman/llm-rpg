"""CommandScope専用のインメモリ取引提案期限切れrepository provider。"""

from __future__ import annotations

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.trade.trade_offer_expiry_command_repository_provider import (
    TradeOfferExpiryCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_repository import (
    ScopeBoundRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_context_unit_of_work_facade import (
    CommandContextUnitOfWorkFacade,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    unwrap_transaction,
)


class InMemoryTradeOfferExpiryCommandRepositoryProvider:
    """同じInMemoryDataStoreのinventoryとitemをscope内だけ公開する。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext[TradeOfferExpiryCommandRepositoryProviderPort],
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        facade = CommandContextUnitOfWorkFacade(unit_of_work, context)
        self._player_inventories = cast(
            PlayerInventoryRepository,
            ScopeBoundRepository(
                InMemoryPlayerInventoryRepository(unit_of_work.data_store, facade),
                self._require_active,
            ),
        )
        self._items = cast(
            ItemRepository,
            ScopeBoundRepository(
                InMemoryItemRepository(unit_of_work.data_store, facade),
                self._require_active,
            ),
        )

    @property
    def player_inventories(self) -> PlayerInventoryRepository:
        self._require_active()
        return self._player_inventories

    @property
    def items(self) -> ItemRepository:
        self._require_active()
        return self._items

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_scoped_repository",
        )


class InMemoryTradeOfferExpiryCommandRepositoryProviderFactory:
    """開始済みインメモリUoWから期限切れ処理用providerを生成する。"""

    def create(
        self,
        context: CommandContext[TradeOfferExpiryCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryTradeOfferExpiryCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリtrade offer expiry providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryTradeOfferExpiryCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
        )


__all__ = [
    "InMemoryTradeOfferExpiryCommandRepositoryProvider",
    "InMemoryTradeOfferExpiryCommandRepositoryProviderFactory",
]
