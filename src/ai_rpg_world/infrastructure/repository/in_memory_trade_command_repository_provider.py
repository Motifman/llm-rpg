"""CommandScope専用のインメモリ取引repository provider。"""

from __future__ import annotations

from typing import Any, cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.trade.trade_command_repository_provider import (
    TradeCommandRepositoryProviderPort,
)
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
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_repository import (
    InMemoryTradeRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_repository import (
    ScopeBoundRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class _CommandContextUnitOfWorkFacade:
    """永続化操作はUoWへ、集約イベントはCommandContextへ送る。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext[TradeCommandRepositoryProviderPort],
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context

    def add_events_from_aggregate(self, aggregate: Any) -> None:
        events = aggregate.get_events()
        self._context.collect_all(events)
        aggregate.clear_events()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._unit_of_work, name)


class InMemoryTradeCommandRepositoryProvider:
    """同じInMemoryDataStoreとUoWへ参加する取引repository束。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext[TradeCommandRepositoryProviderPort],
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        data_store = unit_of_work.data_store
        facade = _CommandContextUnitOfWorkFacade(unit_of_work, context)
        guard = self._require_active
        self._trade_repository = cast(
            TradeRepository,
            ScopeBoundRepository(InMemoryTradeRepository(data_store, facade), guard),
        )
        self._player_inventory_repository = cast(
            PlayerInventoryRepository,
            ScopeBoundRepository(
                InMemoryPlayerInventoryRepository(data_store, facade), guard
            ),
        )
        self._player_status_repository = cast(
            PlayerStatusRepository,
            ScopeBoundRepository(
                InMemoryPlayerStatusRepository(data_store, facade), guard
            ),
        )
        self._player_profile_repository = cast(
            PlayerProfileRepository,
            ScopeBoundRepository(
                InMemoryPlayerProfileRepository(data_store, facade), guard
            ),
        )
        self._item_repository = cast(
            ItemRepository,
            ScopeBoundRepository(InMemoryItemRepository(data_store, facade), guard),
        )

    @property
    def trades(self) -> TradeRepository:
        self._require_active()
        return self._trade_repository

    @property
    def player_inventories(self) -> PlayerInventoryRepository:
        self._require_active()
        return self._player_inventory_repository

    @property
    def player_statuses(self) -> PlayerStatusRepository:
        self._require_active()
        return self._player_status_repository

    @property
    def player_profiles(self) -> PlayerProfileRepository:
        self._require_active()
        return self._player_profile_repository

    @property
    def items(self) -> ItemRepository:
        self._require_active()
        return self._item_repository

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_scoped_repository",
        )


class InMemoryTradeCommandRepositoryProviderFactory:
    """開始済みインメモリUoWから取引providerを生成する。"""

    def create(
        self,
        context: CommandContext[TradeCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryTradeCommandRepositoryProvider:
        if not isinstance(transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリ取引repository providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryTradeCommandRepositoryProvider(
            transaction.unit_of_work,
            context,
        )


__all__ = [
    "InMemoryTradeCommandRepositoryProvider",
    "InMemoryTradeCommandRepositoryProviderFactory",
]
