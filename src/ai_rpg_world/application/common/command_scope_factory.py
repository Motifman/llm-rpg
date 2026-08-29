"""commandごとに新しいCommandScopeを組み立てるfactory。"""

from __future__ import annotations

from typing import Generic, Protocol, TypeVar

from ai_rpg_world.application.common.command_scope import (
    AfterCommitHandoffPort,
    CommandScope,
    RepositoryProviderFactoryPort,
    SyncDomainEventDispatcherPort,
    TransactionPort,
)
from ai_rpg_world.application.common.transactional_outbox import (
    TransactionalOutboxPort,
)


RepositoryProviderT = TypeVar("RepositoryProviderT")


class TransactionFactoryPort(Protocol):
    """commandごとに未開始のtransaction adapterを生成するport。"""

    def create(self) -> TransactionPort:
        """再利用されていないtransaction adapterを返す。"""
        ...


class CommandScopeFactoryPort(Protocol[RepositoryProviderT]):
    """commandごとに一度だけ使えるCommandScopeを生成するport。"""

    def create(self) -> CommandScope[RepositoryProviderT]:
        """NEW状態のCommandScopeを返す。"""
        ...


class CommandScopeFactory(Generic[RepositoryProviderT]):
    """transactionとrepository生成境界を同じCommandScopeへ結び付ける。"""

    def __init__(
        self,
        transaction_factory: TransactionFactoryPort,
        *,
        sync_dispatcher: SyncDomainEventDispatcherPort,
        after_commit_handoff: AfterCommitHandoffPort,
        repository_provider_factory: RepositoryProviderFactoryPort[
            RepositoryProviderT
        ] | None = None,
        transactional_outbox: TransactionalOutboxPort | None = None,
        max_sync_events: int = 1000,
    ) -> None:
        self._transaction_factory = transaction_factory
        self._sync_dispatcher = sync_dispatcher
        self._after_commit_handoff = after_commit_handoff
        self._repository_provider_factory = repository_provider_factory
        self._transactional_outbox = transactional_outbox
        self._max_sync_events = max_sync_events

    def create(self) -> CommandScope[RepositoryProviderT]:
        """新しいtransaction adapterを持つ一度限りのscopeを生成する。"""
        return CommandScope(
            self._transaction_factory.create(),
            sync_dispatcher=self._sync_dispatcher,
            after_commit_handoff=self._after_commit_handoff,
            repository_provider_factory=self._repository_provider_factory,
            transactional_outbox=self._transactional_outbox,
            max_sync_events=self._max_sync_events,
        )


__all__ = [
    "CommandScopeFactory",
    "CommandScopeFactoryPort",
    "TransactionFactoryPort",
]
