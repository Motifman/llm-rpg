"""インメモリ取引providerがscopeと同じUoWへ参加する契約を保証する。"""

import pytest

from ai_rpg_world.application.common.command_scope import CommandContext, CommandScope
from ai_rpg_world.application.common.events import DomainEventCollector
from ai_rpg_world.application.common.exceptions import CommandScopeStateException
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
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


class _RecordingSyncDispatcher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def dispatch(self, event: object, context: object) -> None:
        self.events.append(event)


class _RecordingAfterCommitHandoff:
    def __init__(self) -> None:
        self.events: tuple[object, ...] = ()

    def handoff(self, events: object) -> None:
        self.events = tuple(events)  # type: ignore[arg-type]


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


def test_saved_aggregate_events_move_only_to_command_context() -> None:
    """インメモリrepositoryも旧UoWを経由せず、集約eventを一度だけhandoffする。"""
    data_store = InMemoryDataStore()
    unit_of_work = InMemoryUnitOfWork(data_store=data_store)
    transaction = InMemoryUnitOfWorkTransactionAdapter(unit_of_work)
    dispatcher = _RecordingSyncDispatcher()
    handoff = _RecordingAfterCommitHandoff()
    scope = CommandScope(
        transaction,
        sync_dispatcher=dispatcher,  # type: ignore[arg-type]
        after_commit_handoff=handoff,  # type: ignore[arg-type]
        repository_provider_factory=(
            InMemoryTradeCommandRepositoryProviderFactory()
        ),
    )
    profile = PlayerProfileAggregate.create(PlayerId(1), PlayerName("Alice"))
    profile.change_name(PlayerName("Alicia"))
    pending_event = profile.get_events()[0]

    with scope as context:
        context.repositories.player_profiles.save(profile)
        assert profile.get_events() == []
        assert unit_of_work.has_pending_events() is False

    assert dispatcher.events == [pending_event]
    assert handoff.events == (pending_event,)


def test_provider_uses_shared_command_context_event_sink() -> None:
    """インメモリproviderは旧UoWのevent APIを透過せず、共通sinkだけを収集入口にする。"""
    import ast
    import inspect

    from ai_rpg_world.infrastructure.repository import (
        in_memory_trade_command_repository_provider as module,
    )

    tree = ast.parse(inspect.getsource(module._CommandContextUnitOfWorkFacade))
    method_names = {
        node.name
        for node in tree.body[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "__getattr__" not in method_names
    assert "add_events" not in method_names
    assert "add_events_from_aggregate" in method_names
