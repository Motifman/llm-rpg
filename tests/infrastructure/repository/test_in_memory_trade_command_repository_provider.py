"""インメモリ取引providerがscopeと同じUoWへ参加する契約を保証する。"""

import pytest

from ai_rpg_world.application.common.command_scope import CommandContext, CommandScope
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_trade_command_repository_provider import (
    InMemoryTradeCommandRepositoryProviderFactory,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
)


class _NoOpSyncDispatcher:
    def dispatch(self, event: object, context: object) -> None:
        return


class _NoOpHandoff:
    def handoff(self, events: object) -> None:
        return


def _scope(data_store: InMemoryDataStore) -> CommandScope:
    transaction = InMemoryUnitOfWorkTransactionAdapter(
        InMemoryUnitOfWork(data_store=data_store)
    )
    return CommandScope(
        transaction,
        sync_dispatcher=_NoOpSyncDispatcher(),  # type: ignore[arg-type]
        after_commit_handoff=_NoOpHandoff(),  # type: ignore[arg-type]
        repository_provider_factory=(
            InMemoryTradeCommandRepositoryProviderFactory()
        ),
    )


def test_repository_acquired_in_scope_cannot_be_used_after_scope_closes() -> None:
    """scope内で取得したrepositoryはcommit後の読取りにも再利用できない。"""
    scope = _scope(InMemoryDataStore())

    with scope as context:
        repository = context.repositories.trades
        repository.find_all()

    with pytest.raises(CommandScopeStateException):
        repository.find_all()


def test_factory_rejects_transaction_other_than_in_memory_adapter() -> None:
    """provider factoryは別永続化方式のtransactionとの誤配線を拒否する。"""
    factory = InMemoryTradeCommandRepositoryProviderFactory()
    context = CommandContext(DomainEventCollector())

    with pytest.raises(TypeError, match="InMemoryUnitOfWorkTransactionAdapter"):
        factory.create(context, object())  # type: ignore[arg-type]
