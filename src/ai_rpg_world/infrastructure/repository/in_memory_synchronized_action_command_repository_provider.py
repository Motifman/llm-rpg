"""同期操作group用のscope専用インメモリrepository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.synchronized_action_command_repository_provider import (
    SynchronizedActionCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
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


class InMemorySynchronizedActionCommandRepositoryProvider:
    """同じcommandが使うSpotGraph repositoryをscope寿命へ束縛する。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext,
        *,
        spot_graph: ISpotGraphRepository,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        self._spot_graph = cast(
            ISpotGraphRepository,
            ScopeBoundRepository(spot_graph, self._require_active),
        )

    @property
    def spot_graph(self) -> ISpotGraphRepository:
        self._require_active()
        return self._spot_graph

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_synchronized_action_repository",
        )


class InMemorySynchronizedActionCommandRepositoryProviderFactory:
    """開始済みインメモリUoWから同期操作用providerを生成する。"""

    def __init__(self, *, spot_graph: ISpotGraphRepository) -> None:
        self._spot_graph = spot_graph

    def create(
        self,
        context: CommandContext[SynchronizedActionCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemorySynchronizedActionCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリsynchronized action providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemorySynchronizedActionCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
            spot_graph=self._spot_graph,
        )


__all__ = [
    "InMemorySynchronizedActionCommandRepositoryProvider",
    "InMemorySynchronizedActionCommandRepositoryProviderFactory",
]
