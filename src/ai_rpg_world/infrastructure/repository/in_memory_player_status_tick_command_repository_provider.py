"""CommandScope専用のインメモリplayer status tick repository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.player_status_tick_command_repository_provider import (
    PlayerStatusTickCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
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


class InMemoryPlayerStatusTickCommandRepositoryProvider:
    """同じInMemoryDataStore上のplayer statusをscope内だけ公開する。"""

    def __init__(
        self,
        unit_of_work: InMemoryUnitOfWork,
        context: CommandContext,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._context = context
        facade = CommandContextUnitOfWorkFacade(unit_of_work, context)
        self._player_statuses = cast(
            PlayerStatusRepository,
            ScopeBoundRepository(
                InMemoryPlayerStatusRepository(unit_of_work.data_store, facade),
                self._require_active,
            ),
        )

    @property
    def player_statuses(self) -> PlayerStatusRepository:
        self._require_active()
        return self._player_statuses

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_scoped_repository",
        )


class InMemoryPlayerStatusTickCommandRepositoryProviderFactory:
    """開始済みインメモリUoWからplayer status用providerを生成する。"""

    def create(
        self,
        context: CommandContext[PlayerStatusTickCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryPlayerStatusTickCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリplayer status tick providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryPlayerStatusTickCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
        )


__all__ = [
    "InMemoryPlayerStatusTickCommandRepositoryProvider",
    "InMemoryPlayerStatusTickCommandRepositoryProviderFactory",
]
