"""
SqliteUnitOfWork — 1 UoW スコープで 1 つの sqlite3.Connection とトランザクションを共有する。

`begin` / `commit` / `rollback` を SQLite のトランザクションに対応付け、参加リポジトリは
`connection` プロパティ経由で同一 Connection を使う。リポジトリ側の `commit()` は
ReadModel 等は `Sqlite*Repository.for_shared_unit_of_work(connection)` で共有し、永続化の確定は UoW の `commit` に任せる。

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


class SqliteCommittedCleanupError(RuntimeError):
    """SQLite commit成功後のconnection解放失敗を表す。"""

    def __init__(self, cleanup_error: BaseException) -> None:
        self.cleanup_error = cleanup_error
        super().__init__("SQLite commit後のconnection解放に失敗しました")


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
        self._poisoned = False

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

    @property
    def is_poisoned(self) -> bool:
        """transaction結果が不明で再利用禁止ならTrueを返す。"""
        return self._poisoned

    def begin(self) -> None:
        if self._poisoned:
            raise RuntimeError("結果不明になったSQLite UnitOfWorkは再利用できません")
        if self._in_transaction:
            raise RuntimeError("Transaction already in progress")
        try:
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
        except BaseException:
            if self._owns_connection and self._conn is not None:
                try:
                    self._conn.close()
                except BaseException:
                    self._poisoned = True
                finally:
                    self._conn = None
            raise
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
            self.commit_transaction()
        except Exception:
            if self._in_transaction:
                self.rollback()
            raise

    def commit_transaction(self) -> None:
        """同期配送や自動rollbackを行わず、SQLite transactionだけを確定する。"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        assert self._conn is not None

        self._conn.commit()
        self._committed = True
        self._committed_events = self._pending_events.copy()
        self._pending_events.clear()
        self._processed_sync_count = 0
        self._in_transaction = False
        if self._owns_connection:
            try:
                self._conn.close()
            except BaseException as cleanup_error:
                self._poisoned = True
                self._conn = None
                raise SqliteCommittedCleanupError(cleanup_error) from cleanup_error
            self._conn = None

    def rollback(self) -> None:
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        assert self._conn is not None
        rollback_error: Optional[BaseException] = None
        cleanup_error: Optional[BaseException] = None
        try:
            self._conn.rollback()
        except BaseException as error:
            rollback_error = error
            self._poisoned = True
        finally:
            self._pending_events.clear()
            self._processed_sync_count = 0
            self._committed = False
            self._in_transaction = False
            if self._owns_connection and self._conn is not None:
                try:
                    self._conn.close()
                except BaseException as error:
                    cleanup_error = error
                    self._poisoned = True
                self._conn = None
        if rollback_error is not None:
            raise rollback_error
        if cleanup_error is not None:
            raise cleanup_error

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

    def has_pending_events(self) -> bool:
        """旧Unit of Work側に未回収イベントが残っていればTrueを返す。"""
        return bool(self._pending_events)

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

    def is_in_transaction(self) -> bool:
        return self._in_transaction

    def execute_pending_operations(self) -> None:
        """`SyncEventDispatcher` / InMemory UoW との整合。SQLite は即時 SQL のため保留なし。"""
        return

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


__all__ = [
    "SqliteCommittedCleanupError",
    "SqliteUnitOfWork",
    "SqliteUnitOfWorkFactory",
]
