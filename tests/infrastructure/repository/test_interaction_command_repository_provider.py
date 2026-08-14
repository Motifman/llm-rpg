"""物体interaction用providerがscopeと同じ永続化資源だけを使うことを保証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.common.command_scope import CommandContext, CommandScope
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_interaction_command_repository_provider import (
    InMemoryInteractionCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_interaction_command_repository_provider import (
    SqliteInteractionCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class _NoOpDispatcher:
    def dispatch(self, event: object, context: object) -> None:
        return

    def handoff(self, events: object) -> None:
        return


def _in_memory_factory() -> InMemoryInteractionCommandRepositoryProviderFactory:
    return InMemoryInteractionCommandRepositoryProviderFactory(
        spot_graph=InMemorySpotGraphRepository(
            SpotGraphAggregate.empty(SpotGraphId.create(1))
        ),
        item_specs=InMemoryItemSpecRepository(),
    )


def test_in_memory_provider_rejects_repository_use_after_scope_closes() -> None:
    """scope内で取得した物体interaction repositoryは終了後に再利用できない。"""
    store = InMemoryDataStore()
    dispatcher = _NoOpDispatcher()
    scope = CommandScope(
        InMemoryUnitOfWorkTransactionAdapter(InMemoryUnitOfWork(data_store=store)),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=_in_memory_factory(),
    )

    with scope as context:
        repository = context.repositories.spot_interiors
        repository.find_by_spot_id

    with pytest.raises(CommandScopeStateException):
        repository.find_by_spot_id(None)  # type: ignore[arg-type]


def test_in_memory_factory_rejects_a_different_transaction_kind() -> None:
    """インメモリproviderと別永続化方式の誤配線は開始時に停止する。"""
    context = CommandContext(DomainEventCollector())

    with pytest.raises(TypeError, match="InMemoryUnitOfWorkTransactionAdapter"):
        _in_memory_factory().create(context, object())  # type: ignore[arg-type]


def test_sqlite_provider_uses_one_active_connection_without_independent_commit(
    tmp_path: Path,
) -> None:
    """SQLiteの6repositoryは同じ接続を共有し、書込み側は独自commitしない。"""
    database = tmp_path / "game.db"
    unit_of_work = SqliteUnitOfWork(database)
    dispatcher = _NoOpDispatcher()
    scope = CommandScope(
        SqliteUnitOfWorkTransactionAdapter(unit_of_work),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=SqliteInteractionCommandRepositoryProviderFactory(),
    )

    with scope as context:
        provider = context.repositories
        repositories = (
            provider.spot_graph,
            provider.spot_interiors,
            provider.player_inventories,
            provider.player_statuses,
            provider.items,
            provider.item_specs,
        )
        assert {
            id(repository._repository._conn)  # type: ignore[attr-defined]
            for repository in repositories
        } == {id(unit_of_work.connection)}
        assert all(
            repository._repository._commits_after_write is False  # type: ignore[attr-defined]
            for repository in repositories[:-1]
        )


def test_sqlite_factory_rejects_a_different_transaction_kind() -> None:
    """SQLite providerと別永続化方式の誤配線は開始時に停止する。"""
    context = CommandContext(DomainEventCollector())

    with pytest.raises(TypeError, match="SqliteUnitOfWorkTransactionAdapter"):
        SqliteInteractionCommandRepositoryProviderFactory().create(
            context,
            object(),  # type: ignore[arg-type]
        )
