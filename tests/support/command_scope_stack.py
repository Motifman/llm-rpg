"""旧サービスの入出力を保ちながら、試験の確定をCommandScopeで行う。"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from types import TracebackType
from typing import Any

from ai_rpg_world.application.common.command_scope import CommandScope
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
)
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.infrastructure.events.command_event_dispatcher import CommandEventDispatcher
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.command_context_unit_of_work_facade import CommandContextUnitOfWorkFacade
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from tests.support.trace_recorders import CollectingTraceRecorder


class CommandScopeTestStack:
    """サービスには既存の口を渡し、収集と確定後の記録を共通基盤へ委ねる。"""

    def __init__(self, store: InMemoryDataStore) -> None:
        self.store = store
        self._transaction = InMemoryUnitOfWork(data_store=store)
        self.trace = CollectingTraceRecorder()
        isolator = WorldTickFailureIsolator(
            policy=WorldTickFailurePolicy.ISOLATE, trace_recorder_provider=lambda: self.trace
        )
        self.dispatcher = CommandEventDispatcher(
            failure_observer=isolator.after_commit_failure_observer(tick_provider=lambda: None)
        )
        self._published: list[DomainEvent] = []

    def __enter__(self) -> CommandScopeTestStack:
        self._scope = CommandScope(
            InMemoryUnitOfWorkTransactionAdapter(self._transaction),
            sync_dispatcher=self.dispatcher,
            after_commit_handoff=self,
        )
        self._context = self._scope.__enter__()
        self._facade = CommandContextUnitOfWorkFacade(self._transaction, self._context)
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._scope.__exit__(exc_type, exc, tb)

    def add_events_from_aggregate(self, aggregate: Any) -> None:
        self._facade.add_events_from_aggregate(aggregate)

    def publish(self, event: DomainEvent) -> None:
        self._context.collect(event)

    def publish_all(self, events: Iterable[DomainEvent]) -> None:
        self._context.collect_all(events)

    def handoff(self, events: Sequence[DomainEvent]) -> None:
        self._published.extend(events)
        self.dispatcher.handoff(events)

    def get_published_events(self) -> list[DomainEvent]:
        return list(self._published)

    def clear_events(self) -> None:
        self._published.clear()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._transaction, name)
