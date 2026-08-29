"""CommandScope専用の取引書込みrepository provider。"""

from __future__ import annotations

from typing import cast

from ai_rpg_world.application.common.aggregate_event_sink import (
    CommandContextAggregateEventSink,
)
from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.common.command_scope import TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
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
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
    SqlitePlayerProfileWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_aggregate_repository import (
    SqliteTradeAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_repository import (
    ScopeBoundRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    unwrap_transaction,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class SqliteTradeCommandRepositoryProvider:
    """同一SQLite transactionへ参加する取引書込みrepository束。"""

    def __init__(
        self,
        unit_of_work: SqliteUnitOfWork,
        context: CommandContext["SqliteTradeCommandRepositoryProvider"],
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        connection = unit_of_work.connection
        guard = self._require_active
        event_sink = CommandContextAggregateEventSink(
            context,
            is_active=unit_of_work.is_in_transaction,
        )
        self._trade_repository = cast(
            TradeRepository,
            ScopeBoundRepository(
                SqliteTradeAggregateRepository.for_shared_unit_of_work(
                    connection,
                    event_sink=event_sink,
                ),
                guard,
            ),
        )
        self._player_inventory_repository = cast(
            PlayerInventoryRepository,
            ScopeBoundRepository(
                SqlitePlayerInventoryWriteRepository.for_shared_unit_of_work(
                    connection,
                    event_sink=event_sink,
                ),
                guard,
            ),
        )
        self._player_status_repository = cast(
            PlayerStatusRepository,
            ScopeBoundRepository(
                SqlitePlayerStatusWriteRepository.for_shared_unit_of_work(
                    connection,
                    event_sink=event_sink,
                ),
                guard,
            ),
        )
        self._player_profile_repository = cast(
            PlayerProfileRepository,
            ScopeBoundRepository(
                SqlitePlayerProfileWriteRepository.for_shared_unit_of_work(
                    connection,
                    event_sink=event_sink,
                ),
                guard,
            ),
        )
        self._item_repository = cast(
            ItemRepository,
            ScopeBoundRepository(
                SqliteItemWriteRepository.for_shared_unit_of_work(
                    connection,
                    event_sink=event_sink,
                ),
                guard,
            ),
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


class SqliteTradeCommandRepositoryProviderFactory:
    """開始済みSqliteUnitOfWorkから取引repository providerを生成する。"""

    def create(
        self,
        context: CommandContext[SqliteTradeCommandRepositoryProvider],
        transaction: TransactionPort,
    ) -> SqliteTradeCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, SqliteUnitOfWorkTransactionAdapter):
            raise TypeError(
                "SQLite取引repository providerには"
                "SqliteUnitOfWorkTransactionAdapterが必要です"
            )
        return SqliteTradeCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
        )


__all__ = [
    "SqliteTradeCommandRepositoryProvider",
    "SqliteTradeCommandRepositoryProviderFactory",
]
