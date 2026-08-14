"""give_item用providerが同じtransaction資源だけを公開する契約。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.common.command_scope import CommandContext
from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.infrastructure.events.command_event_dispatcher import CommandEventDispatcher
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_transfer_command_repository_provider import InMemoryItemTransferCommandRepositoryProviderFactory
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import InMemorySpotGraphRepository
from ai_rpg_world.infrastructure.repository.sqlite_item_transfer_command_repository_provider import SqliteItemTransferCommandRepositoryProviderFactory
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionFactory,
    SqliteUnitOfWorkTransactionAdapter,
    SqliteUnitOfWorkTransactionFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionAdapter,
    RollbackParticipantTransactionFactory,
)
from tests.application.world_graph.test_spot_graph_item_transfer_service import (
    PLAYER_ID,
    SPOT_ID,
    _make_graph_with_player,
)


def _dispatcher() -> CommandEventDispatcher:
    return CommandEventDispatcher()


class _Participant:
    """provider接続だけを検証するための単純なrollback参加資源。"""

    rollback_resource = object()

    def acquire_rollback_ownership(self) -> None:
        return

    def release_rollback_ownership(self) -> None:
        return

    def take_rollback_snapshot(self) -> None:
        return None

    def restore_rollback_snapshot(self, snapshot: object) -> None:
        return

    def poison_after_rollback_failure(self, error: BaseException) -> None:
        return


def test_in_memory_provider_rejects_repository_use_after_scope() -> None:
    """インメモリproviderのrepositoryはcommand終了後に再利用できない。"""
    dispatcher = _dispatcher()
    factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(InMemoryDataStore()),
            participants=(_Participant(),),
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
        repository_provider_factory=(
            InMemoryItemTransferCommandRepositoryProviderFactory(
                InMemorySpotGraphRepository(
                    _make_graph_with_player(SPOT_ID, (PLAYER_ID,))
                )
            )
        ),
    )

    with factory.create() as context:
        inventories = context.repositories.player_inventories
        interiors = context.repositories.spot_interiors
        assert not hasattr(context.repositories.spot_graph, "save")

    with pytest.raises(CommandScopeStateException):
        inventories.find_by_id(PLAYER_ID)
    with pytest.raises(CommandScopeStateException):
        interiors.find_by_spot_id(SPOT_ID)


def test_sqlite_provider_repositories_share_scope_connection(tmp_path) -> None:
    """SQLiteの5repositoryは開始済みUoWの同一接続を共有し独自commitしない。"""
    database = tmp_path / "game.db"
    dispatcher = _dispatcher()
    transaction = SqliteUnitOfWorkTransactionFactory(database).create()
    composed_transaction = RollbackParticipantTransactionAdapter(
        transaction,
        participants=(_Participant(),),
    )
    composed_transaction.begin()
    context = CommandContext(DomainEventCollector())
    provider = SqliteItemTransferCommandRepositoryProviderFactory().create(
        context,
        composed_transaction,
    )
    repositories = (
        provider.player_inventories,
        provider.player_statuses,
        provider.items,
        provider.spot_graph,
        provider.spot_interiors,
    )

    try:
        assert isinstance(transaction, SqliteUnitOfWorkTransactionAdapter)
        assert {
            id(repository._repository._conn)  # type: ignore[attr-defined]
            for repository in repositories
        } == {id(transaction.unit_of_work.connection)}
        assert all(
            repository._repository._commits_after_write is False  # type: ignore[attr-defined]
            for repository in repositories
        )
    finally:
        composed_transaction.rollback()


def test_sqlite_factory_rejects_non_sqlite_transaction() -> None:
    """SQLite providerは別種類のtransactionとの誤配線を開始時に拒否する。"""
    context = CommandContext(DomainEventCollector())

    with pytest.raises(TypeError, match="SqliteUnitOfWorkTransactionAdapter"):
        SqliteItemTransferCommandRepositoryProviderFactory().create(
            context,
            object(),  # type: ignore[arg-type]
        )
