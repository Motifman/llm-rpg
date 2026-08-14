"""CommandScope専用のインメモリinteraction repository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.interaction_command_repository_provider import (
    InteractionCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.repository.item_spec_repository import ItemSpecRepository
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


class InMemoryInteractionCommandRepositoryProvider:
    """同じInMemoryDataStoreとrollback参加資源を使うrepository束。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext,
        *,
        spot_graph: ISpotGraphRepository,
        item_specs: ItemSpecRepository,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        guard = self._require_active
        facade = CommandContextUnitOfWorkFacade(unit_of_work, context)
        store = unit_of_work.data_store
        self._spot_graph = cast(
            ISpotGraphRepository, ScopeBoundRepository(spot_graph, guard)
        )
        self._spot_interiors = cast(
            ISpotInteriorRepository,
            ScopeBoundRepository(InMemorySpotInteriorRepository(data_store=store), guard),
        )
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
        self._item_specs = cast(
            ItemSpecRepository, ScopeBoundRepository(item_specs, guard)
        )

    @property
    def spot_graph(self) -> ISpotGraphRepository:
        self._require_active()
        return self._spot_graph

    @property
    def spot_interiors(self) -> ISpotInteriorRepository:
        self._require_active()
        return self._spot_interiors

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
    def item_specs(self) -> ItemSpecRepository:
        self._require_active()
        return self._item_specs

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_scoped_repository",
        )


class InMemoryInteractionCommandRepositoryProviderFactory:
    """開始済みインメモリUoWからinteraction用providerを生成する。"""

    def __init__(
        self,
        *,
        spot_graph: ISpotGraphRepository,
        item_specs: ItemSpecRepository,
    ) -> None:
        self._spot_graph = spot_graph
        self._item_specs = item_specs

    def create(
        self,
        context: CommandContext[InteractionCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryInteractionCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリinteraction providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryInteractionCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
            spot_graph=self._spot_graph,
            item_specs=self._item_specs,
        )


__all__ = [
    "InMemoryInteractionCommandRepositoryProvider",
    "InMemoryInteractionCommandRepositoryProviderFactory",
]
