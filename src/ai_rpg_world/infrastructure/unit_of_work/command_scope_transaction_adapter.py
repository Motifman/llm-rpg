"""既存Unit of WorkをCommandScopeのTransactionPortへ適合させるadapter。"""

from __future__ import annotations

from ai_rpg_world.application.common.exceptions import (
    TransactionCommittedCleanupException,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryCommittedCleanupError,
    InMemoryUnitOfWork,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteCommittedCleanupError,
    SqliteUnitOfWork,
)


class InMemoryUnitOfWorkTransactionAdapter:
    """イベント責務を除いたインメモリtransactionだけを公開する。"""

    def __init__(self, unit_of_work: InMemoryUnitOfWork) -> None:
        if unit_of_work.sync_event_dispatcher is not None:
            raise ValueError(
                "CommandScope用adapterにはsync_event_dispatcher未設定の"
                "InMemoryUnitOfWorkが必要です"
            )
        if not unit_of_work.supports_atomic_rollback:
            raise ValueError(
                "CommandScope用InMemoryUnitOfWorkにはrollback用data_storeが必要です"
            )
        self._unit_of_work = unit_of_work

    @property
    def is_active(self) -> bool:
        """元Unit of Workのtransactionが有効ならTrueを返す。"""
        return self._unit_of_work.is_in_transaction()

    def begin(self) -> None:
        """インメモリtransactionを開始する。"""
        self._unit_of_work.begin()

    def commit(self) -> None:
        """イベント配送と自動rollbackを行わずtransactionを確定する。"""
        self._require_no_legacy_events()
        self._unit_of_work.execute_pending_operations()
        self._require_no_legacy_events()
        try:
            self._unit_of_work.commit_transaction()
        except InMemoryCommittedCleanupError as error:
            raise TransactionCommittedCleanupException(
                cleanup_error=error.cleanup_error,
            ) from error

    def _require_no_legacy_events(self) -> None:
        if self._unit_of_work.has_pending_events():
            raise RuntimeError(
                "旧Unit of Workに未回収イベントがあります。"
                "CommandContextへ収集してください"
            )

    def rollback(self) -> None:
        """未確定変更をsnapshotへ戻す。"""
        self._unit_of_work.rollback()


class SqliteUnitOfWorkTransactionAdapter:
    """イベント責務を除いたSQLite transactionだけを公開する。"""

    def __init__(self, unit_of_work: SqliteUnitOfWork) -> None:
        if unit_of_work.sync_event_dispatcher is not None:
            raise ValueError(
                "CommandScope用adapterにはsync_event_dispatcher未設定の"
                "SqliteUnitOfWorkが必要です"
            )
        self._unit_of_work = unit_of_work

    @property
    def unit_of_work(self) -> SqliteUnitOfWork:
        """scope専用資源の生成元となる同一UnitOfWorkを返す。"""
        return self._unit_of_work

    @property
    def is_active(self) -> bool:
        """元Unit of Workのtransactionが有効ならTrueを返す。"""
        return self._unit_of_work.is_in_transaction()

    def begin(self) -> None:
        """SQLite transactionを開始する。"""
        self._unit_of_work.begin()

    def commit(self) -> None:
        """イベント配送と自動rollbackを行わずtransactionを確定する。"""
        if self._unit_of_work.has_pending_events():
            raise RuntimeError(
                "旧Unit of Workに未回収イベントがあります。"
                "CommandContextへ収集してください"
            )
        try:
            self._unit_of_work.commit_transaction()
        except SqliteCommittedCleanupError as error:
            raise TransactionCommittedCleanupException(
                cleanup_error=error.cleanup_error,
            ) from error

    def rollback(self) -> None:
        """未確定SQLを破棄する。"""
        self._unit_of_work.rollback()


__all__ = [
    "InMemoryUnitOfWorkTransactionAdapter",
    "SqliteUnitOfWorkTransactionAdapter",
]
