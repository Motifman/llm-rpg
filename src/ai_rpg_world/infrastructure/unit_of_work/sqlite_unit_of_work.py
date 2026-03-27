"""
SqliteUnitOfWork — 1 UoW スコープで 1 つの sqlite3.Connection とトランザクションを共有する。

`begin` / `commit` / `rollback` を SQLite のトランザクションに対応付け、参加リポジトリは
`connection` プロパティ経由で同一 Connection を使う。リポジトリ側の `commit()` は
`autocommit=False` 等で抑止し、永続化の確定は UoW の `commit` に任せる。

イベント関連 API は `UnitOfWork` Protocol および `TransactionalScope` との整合のため
`InMemoryUnitOfWork` と同形の状態を保持する（同期 dispatcher は任意注入）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

import sqlite3

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory


class SqliteUnitOfWork(UnitOfWork):
    """SQLite 実装の Unit of Work"""

    def __init__(
        self,
        database: Union[str, Path, None] = None,
        *,
        connection: Optional[sqlite3.Connection] = None,
        sync_event_dispatcher: Any = None,
    ) -> None:
        if (database is None) == (connection is None):
            raise ValueError("database と connection のどちらか一方だけを指定してください")
        self._database: Optional[str] = str(database) if database is not None else None
        self._supplied: Optional[sqlite3.Connection] = connection
        self._owns_connection = connection is None
        self._conn: Optional[sqlite3.Connection] = None
        self._in_transaction = False
        self._pending_events: List[BaseDomainEvent[Any, Any]] = []
        self._processed_sync_count = 0
        self._committed = False
        self._committed_events: List[BaseDomainEvent[Any, Any]] = []
        self._sync_event_dispatcher = sync_event_dispatcher

    @property
    def sync_event_dispatcher(self) -> Any:
        return self._sync_event_dispatcher

    @property
    def connection(self) -> sqlite3.Connection:
        if not self._in_transaction or self._conn is None:
            raise RuntimeError(
                "アクティブな SQLite トランザクションがありません（begin または with uow を先に呼び出してください）"
            )
        return self._conn

    def begin(self) -> None:
        if self._in_transaction:
            raise RuntimeError("Transaction already in progress")
        if self._owns_connection:
            assert self._database is not None
            path = self._database
            if path != ":memory:":
                Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path)
            self._conn.row_factory = sqlite3.Row
        else:
            self._conn = self._supplied
            if self._conn is None:
                raise RuntimeError("connection が設定されていません")
            if self._conn.row_factory is not sqlite3.Row:
                self._conn.row_factory = sqlite3.Row
        self._conn.execute("BEGIN")
        self._in_transaction = True
        self._pending_events = []
        self._processed_sync_count = 0
        self._committed = False
        self._committed_events = []

    def commit(self) -> None:
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        assert self._conn is not None
        try:
            if self._sync_event_dispatcher is not None:
                self._sync_event_dispatcher.flush_sync_events()
            self._conn.commit()
            self._committed = True
        except Exception:
            self.rollback()
            raise
        finally:
            events_snapshot = self._pending_events.copy()
            if self._committed:
                self._committed_events = events_snapshot.copy()
            self._pending_events.clear()
            self._processed_sync_count = 0
            self._in_transaction = False
            if self._owns_connection and self._conn is not None:
                self._conn.close()
                self._conn = None

    def rollback(self) -> None:
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        assert self._conn is not None
        try:
            self._conn.rollback()
        finally:
            self._pending_events.clear()
            self._processed_sync_count = 0
            self._committed = False
            self._in_transaction = False
            if self._owns_connection and self._conn is not None:
                self._conn.close()
                self._conn = None

    def add_events(self, events: List[BaseDomainEvent[Any, Any]]) -> None:
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_events.extend(events)

    def add_events_from_aggregate(self, aggregate: Any) -> None:
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        if hasattr(aggregate, "get_events") and hasattr(aggregate, "clear_events"):
            events = aggregate.get_events()
            if events:
                self._pending_events.extend(events)
            aggregate.clear_events()

    def get_sync_processed_count(self) -> int:
        return self._processed_sync_count

    def get_pending_events_since(
        self, processed_count: int
    ) -> Tuple[List[BaseDomainEvent[Any, Any]], int]:
        events = self._pending_events[processed_count:]
        return (events, len(self._pending_events))

    def advance_sync_processed_count(self, new_count: int) -> None:
        self._processed_sync_count = new_count

    def get_committed_events(self) -> List[BaseDomainEvent[Any, Any]]:
        return self._committed_events.copy()

    def clear_committed_events(self) -> None:
        self._committed_events.clear()

    def __enter__(self) -> SqliteUnitOfWork:
        self.begin()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.rollback()
        else:
            self.commit()


class SqliteUnitOfWorkFactory(UnitOfWorkFactory):
    """同一 DB パスに対し、都度新しい `SqliteUnitOfWork` を生成する。

    ファイルパス向け。`:memory:` を使う場合は `SqliteUnitOfWork(database=\":memory:\")` を直接生成する。
    """

    def __init__(self, database: Union[str, Path]) -> None:
        raw = str(database)
        if raw == ":memory:":
            self._database = raw
        else:
            self._database = str(Path(database).expanduser().resolve())

    def create(self) -> SqliteUnitOfWork:
        return SqliteUnitOfWork(self._database)


__all__ = ["SqliteUnitOfWork", "SqliteUnitOfWorkFactory"]
