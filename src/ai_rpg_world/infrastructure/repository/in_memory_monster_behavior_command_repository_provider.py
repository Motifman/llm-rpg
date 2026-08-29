"""monster behavior用のscope専用インメモリrepository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.monster.services.monster_behavior_command_repository_provider import (
    MonsterBehaviorCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
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
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
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


class InMemoryMonsterBehaviorCommandRepositoryProvider:
    """同じstoreとgraphからmonster行動用repositoryを生成する。"""

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
        facade = CommandContextUnitOfWorkFacade(unit_of_work, context)
        store = unit_of_work.data_store
        self._monsters = cast(
            MonsterRepository,
            ScopeBoundRepository(
                InMemoryMonsterAggregateRepository(store, facade), guard
            ),
        )
        self._player_statuses = cast(
            PlayerStatusRepository,
            ScopeBoundRepository(InMemoryPlayerStatusRepository(store, facade), guard),
        )
        self._spot_interiors = cast(
            ISpotInteriorRepository,
            ScopeBoundRepository(
                InMemorySpotInteriorRepository(data_store=store), guard
            ),
        )
        self._spot_graph = cast(
            ISpotGraphRepository,
            ScopeBoundRepository(spot_graph, guard),
        )

    @property
    def monsters(self) -> MonsterRepository:
        self._require_active()
        return self._monsters

    @property
    def player_statuses(self) -> PlayerStatusRepository:
        self._require_active()
        return self._player_statuses

    @property
    def spot_interiors(self) -> ISpotInteriorRepository:
        self._require_active()
        return self._spot_interiors

    @property
    def spot_graph(self) -> ISpotGraphRepository:
        self._require_active()
        return self._spot_graph

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_monster_behavior_repository",
        )


class InMemoryMonsterBehaviorCommandRepositoryProviderFactory:
    """開始済みインメモリUoWからmonster行動用providerを生成する。"""

    def __init__(self, *, spot_graph: ISpotGraphRepository) -> None:
        self._spot_graph = spot_graph

    def create(
        self,
        context: CommandContext[MonsterBehaviorCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryMonsterBehaviorCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリmonster behavior providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryMonsterBehaviorCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
            spot_graph=self._spot_graph,
        )


__all__ = [
    "InMemoryMonsterBehaviorCommandRepositoryProvider",
    "InMemoryMonsterBehaviorCommandRepositoryProviderFactory",
]
