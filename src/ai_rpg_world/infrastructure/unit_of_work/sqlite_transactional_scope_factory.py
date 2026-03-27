"""`SqliteUnitOfWork` と `TransactionalScope`・非同期イベント経路の組み立て（テスト・アプリ配線用）。"""
from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any, Tuple

from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork
from ai_rpg_world.infrastructure.unit_of_work.transactional_scope import TransactionalScope

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
        InMemoryEventPublisherWithUow,
    )


def create_sqlite_scope_with_event_publisher(
    *,
    connection: sqlite3.Connection,
) -> Tuple[TransactionalScope, "InMemoryEventPublisherWithUow"]:
    """共有 `sqlite3.Connection` に対し、ReadModel インメモリ経路と同形の scope / publisher を返す。"""
    from ai_rpg_world.infrastructure.events.in_memory_event_publisher_with_uow import (
        InMemoryEventPublisherWithUow,
    )
    from ai_rpg_world.infrastructure.events.in_process_async_event_executor import (
        InProcessAsyncEventExecutor,
    )
    from ai_rpg_world.infrastructure.events.in_process_async_event_transport import (
        InProcessAsyncEventTransport,
    )
    from ai_rpg_world.infrastructure.events.sync_event_dispatcher import SyncEventDispatcher

    unit_of_work = SqliteUnitOfWork(connection=connection)
    scope: Any = TransactionalScope(unit_of_work, None)
    async_executor = InProcessAsyncEventExecutor()
    async_transport = InProcessAsyncEventTransport(async_executor)
    event_publisher = InMemoryEventPublisherWithUow(scope, async_transport=async_transport)
    scope.set_event_publisher(event_publisher)

    sync_event_dispatcher = SyncEventDispatcher(scope, event_publisher)
    scope.set_sync_event_dispatcher(sync_event_dispatcher)
    unit_of_work._sync_event_dispatcher = sync_event_dispatcher  # noqa: SLF001

    return scope, event_publisher


__all__ = ["create_sqlite_scope_with_event_publisher"]
