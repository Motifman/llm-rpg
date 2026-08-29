"""monster spawn用のscope専用インメモリrepository provider。"""

from typing import cast

from ai_rpg_world.application.common.command_scope import CommandContext, TransactionPort
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.application.world_graph.monster_spawn_command_repository_provider import (
    MonsterSpawnCommandRepositoryProviderPort,
)
from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterRepository,
)
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillLoadoutRepository,
)
from ai_rpg_world.domain.world_graph.repository.spot_graph_repository import (
    ISpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_skill_loadout_repository import (
    InMemorySkillLoadoutRepository,
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


class InMemoryMonsterSpawnCommandRepositoryProvider:
    """同じInMemoryDataStoreからspawn用repositoryを生成する。"""

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
        self._skill_loadouts = cast(
            SkillLoadoutRepository,
            ScopeBoundRepository(InMemorySkillLoadoutRepository(store, facade), guard),
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
    def skill_loadouts(self) -> SkillLoadoutRepository:
        self._require_active()
        return self._skill_loadouts

    @property
    def spot_graph(self) -> ISpotGraphRepository:
        self._require_active()
        return self._spot_graph

    def _require_active(self) -> None:
        if self._context.is_open and self._unit_of_work.is_in_transaction():
            return
        raise CommandScopeStateException(
            current_state="closed",
            attempted_operation="use_monster_spawn_repository",
        )


class InMemoryMonsterSpawnCommandRepositoryProviderFactory:
    """開始済みインメモリUoWからspawn用providerを生成する。"""

    def __init__(self, *, spot_graph: ISpotGraphRepository) -> None:
        self._spot_graph = spot_graph

    def create(
        self,
        context: CommandContext[MonsterSpawnCommandRepositoryProviderPort],
        transaction: TransactionPort,
    ) -> InMemoryMonsterSpawnCommandRepositoryProvider:
        base_transaction = unwrap_transaction(transaction)
        if not isinstance(base_transaction, InMemoryUnitOfWorkTransactionAdapter):
            raise TypeError(
                "インメモリmonster spawn providerには"
                "InMemoryUnitOfWorkTransactionAdapterが必要です"
            )
        return InMemoryMonsterSpawnCommandRepositoryProvider(
            base_transaction.unit_of_work,
            context,
            spot_graph=self._spot_graph,
        )


__all__ = [
    "InMemoryMonsterSpawnCommandRepositoryProvider",
    "InMemoryMonsterSpawnCommandRepositoryProviderFactory",
]
