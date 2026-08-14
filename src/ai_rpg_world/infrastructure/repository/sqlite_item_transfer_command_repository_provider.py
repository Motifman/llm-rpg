"""CommandScope専用のSQLiteアイテム受渡しrepository provider。"""

from typing import cast

from ai_rpg_world.application.common.aggregate_event_sink import (
    CommandContextAggregateEventSink,
)
from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.item_transfer_command_repository_provider import (
    SpotGraphReadRepositoryPort,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.player.repository.player_inventory_repository import (
    PlayerInventoryRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_repository import (
    ScopeBoundRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_spot_graph_read_repository import (
    ScopeBoundSpotGraphReadRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_spot_graph_repository import (
    SqliteSpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_spot_interior_repository import (
    SqliteSpotInteriorRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    unwrap_transaction,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class SqliteItemTransferCommandRepositoryProvider:
    """同じSQLite transactionへ参加するgive_item用repository束。"""

    def __init__(self, unit_of_work: SqliteUnitOfWork, context: CommandContext) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        guard = self._require_active
        sink = CommandContextAggregateEventSink(
            context,
            is_active=unit_of_work.is_in_transaction,
        )
        connection = unit_of_work.connection
        self._player_inventories = cast(
            PlayerInventoryRepository,
            ScopeBoundRepository(
                SqlitePlayerInventoryWriteRepository.for_shared_unit_of_work(
                    connection, event_sink=sink
                ),
                guard,
            ),
        )
        self._player_statuses = cast(
            PlayerStatusRepository,
            ScopeBoundRepository(
                SqlitePlayerStatusWriteRepository.for_shared_unit_of_work(
                    connection, event_sink=sink
                ),
                guard,
            ),
        )
        self._items = cast(
            ItemRepository,
            ScopeBoundRepository(
                SqliteItemWriteRepository.for_shared_unit_of_work(
                    connection, event_sink=sink
                ),
                guard,
            ),
        )
        self._spot_graph: SpotGraphReadRepositoryPort = (
            ScopeBoundSpotGraphReadRepository(
                SqliteSpotGraphRepository.for_shared_unit_of_work(connection), guard
            )
        )
        self._spot_interiors = cast(
            ISpotInteriorRepository,
            ScopeBoundRepository(
                SqliteSpotInteriorRepository.for_shared_unit_of_work(connection),
                guard,
            ),
        )

    @property
    def player_inventories(self) -> PlayerInventoryRepository:
        self._require_active()
        return self._player_inventories

    @property
    def player_statuses(self) -> PlayerStatusRepository:
        self._require_active()
        return self._player_statuses

    @property
    def items(self) -> ItemRepository:
        self._require_active()
        return self._items

    @property
    def spot_graph(self) -> SpotGraphReadRepositoryPort:
        self._require_active()
        return self._spot_graph

    @property
    def spot_interiors(self) -> ISpotInteriorRepository:
        self._require_active()
        return self._spot_interiors

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_scoped_repository",
        )


class SqliteItemTransferCommandRepositoryProviderFactory:
    """開始済みSQLite UoWからgive_item用providerを生成する。"""

    def create(
        self,
        context: CommandContext,
        transaction: TransactionPort,
    ) -> SqliteItemTransferCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, SqliteUnitOfWorkTransactionAdapter):
            raise TypeError(
                "SQLiteアイテム受渡しproviderには"
                "SqliteUnitOfWorkTransactionAdapterが必要です"
            )
        return SqliteItemTransferCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
        )


__all__ = [
    "SqliteItemTransferCommandRepositoryProvider",
    "SqliteItemTransferCommandRepositoryProviderFactory",
]
