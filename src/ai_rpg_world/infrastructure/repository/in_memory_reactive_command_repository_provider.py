"""reactive binding用のscope専用インメモリrepository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.reactive_command_repository_provider import (
    ReactiveCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.repository.scope_bound_repository import (
    ScopeBoundRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    unwrap_transaction,
)


class InMemoryReactiveCommandRepositoryProvider:
    """同じstoreとgraphからreactive binding用repositoryを生成する。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext,
        *,
        spot_graph: ISpotGraphRepository,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        guard = self._require_active
        self._spot_graph = cast(
            ISpotGraphRepository,
            ScopeBoundRepository(spot_graph, guard),
        )
        self._spot_interiors = cast(
            ISpotInteriorRepository,
            ScopeBoundRepository(
                InMemorySpotInteriorRepository(data_store=unit_of_work.data_store),
                guard,
            ),
        )

    @property
    def spot_graph(self) -> ISpotGraphRepository:
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
            attempted_operation="use_reactive_repository",
        )


class InMemoryReactiveCommandRepositoryProviderFactory:
    """開始済みインメモリUoWからreactive binding用providerを生成する。"""

    def __init__(self, *, spot_graph: ISpotGraphRepository) -> None:
        self._spot_graph = spot_graph

    def create(
        self,
        context: CommandContext[ReactiveCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryReactiveCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリreactive providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryReactiveCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
            spot_graph=self._spot_graph,
        )


__all__ = [
    "InMemoryReactiveCommandRepositoryProvider",
    "InMemoryReactiveCommandRepositoryProviderFactory",
]
