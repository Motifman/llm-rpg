"""CommandScope専用のインメモリアイテム受渡しrepository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.item_transfer_command_repository_provider import (
    ItemTransferCommandRepositoryProviderPort,
    SpotGraphReadRepositoryPort,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
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
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_repository import (
    ScopeBoundRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_spot_graph_read_repository import (
    ScopeBoundSpotGraphReadRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_context_unit_of_work_facade import (
    CommandContextUnitOfWorkFacade,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class InMemoryItemTransferCommandRepositoryProvider:
    """同じInMemoryDataStoreとUoWへ参加するgive_item用repository束。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext,
        spot_graph: ISpotGraphRepository,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        guard = self._require_active
        facade = CommandContextUnitOfWorkFacade(unit_of_work, context)
        store = unit_of_work.data_store
        self._player_inventories = cast(
            PlayerInventoryRepository,
            ScopeBoundRepository(
                InMemoryPlayerInventoryRepository(store, facade), guard
            ),
        )
        self._player_statuses = cast(
            PlayerStatusRepository,
            ScopeBoundRepository(InMemoryPlayerStatusRepository(store, facade), guard),
        )
        self._items = cast(
            ItemRepository,
            ScopeBoundRepository(InMemoryItemRepository(store, facade), guard),
        )
        self._spot_graph: SpotGraphReadRepositoryPort = (
            ScopeBoundSpotGraphReadRepository(spot_graph, guard)
        )
        self._spot_interiors = cast(
            ISpotInteriorRepository,
            ScopeBoundRepository(
                InMemorySpotInteriorRepository(data_store=store),
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


class InMemoryItemTransferCommandRepositoryProviderFactory:
    """開始済みインメモリUoWからgive_item用providerを生成する。"""

    def __init__(self, spot_graph: ISpotGraphRepository) -> None:
        self._spot_graph = spot_graph

    def create(
        self,
        context: CommandContext,
        transaction: TransactionPort,
    ) -> InMemoryItemTransferCommandRepositoryProvider:
        if not isinstance(transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリアイテム受渡しproviderには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryItemTransferCommandRepositoryProvider(
            transaction.unit_of_work,
            context,
            self._spot_graph,
        )


__all__ = [
    "InMemoryItemTransferCommandRepositoryProvider",
    "InMemoryItemTransferCommandRepositoryProviderFactory",
]
