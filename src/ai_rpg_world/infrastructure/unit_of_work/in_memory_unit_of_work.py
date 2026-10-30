"""
InMemoryUnitOfWork - インメモリ実装のUnit of Work
実際のデータベーストランザクションは存在しないが、論理的なトランザクション境界を提供します。
"""

from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Any

from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryCommittedCleanupError(RuntimeError):
    """インメモリcommit成功後の共有store排他解放失敗を表す。"""

    def __init__(self, cleanup_error: BaseException) -> None:
        self.cleanup_error = cleanup_error
        super().__init__("インメモリcommit後の共有store排他解放に失敗しました")


class InMemoryBeginCleanupError(RuntimeError):
    """snapshot取得と共有store排他解放の二重失敗を表す。"""

    def __init__(
        self,
        *,
        snapshot_error: BaseException,
        cleanup_error: BaseException,
    ) -> None:
        self.snapshot_error = snapshot_error
        self.cleanup_error = cleanup_error
        super().__init__("インメモリtransactionの開始後処理に失敗しました")


class InMemoryUnitOfWork(UnitOfWork):
    """インメモリ実装のUnit of Work

    実際のDBトランザクションはないが、論理的なトランザクション境界を提供し、
    複数の集約更新の一貫性を保証します。
    """

    def __init__(
        self,
        data_store: Any = None,
    ) -> None:
        self._in_transaction = False
        self._pending_operations: list[Callable[[], object]] = []
        self._pending_events: list[DomainEvent] = []
        self._pending_aggregates: dict[tuple[str, Any], Any] = {}  # (repo_key, entity_id) -> 未反映の集約
        self._committed = False
        self._committed_events: list[DomainEvent] = []
        self._data_store = data_store
        self._snapshot = None
        self._transaction_lock_acquired = False
        self._poisoned = False

    @property
    def supports_atomic_rollback(self) -> bool:
        """完全snapshotと排他・隔離契約を持つstoreならTrueを返す。"""
        required = (
            "take_snapshot",
            "restore_snapshot",
            "acquire_uow_transaction",
            "release_uow_transaction",
            "poison_uow_transactions",
        )
        return self._data_store is not None and all(
            callable(getattr(self._data_store, name, None)) for name in required
        )

    @property
    def data_store(self) -> Any:
        """scope専用repositoryが共有するrollback対象storeを返す。"""
        if self._data_store is None:
            raise RuntimeError("InMemoryUnitOfWorkにdata_storeが設定されていません")
        return self._data_store

    @property
    def is_poisoned(self) -> bool:
        """復元失敗によりこのUoWを再利用できないならTrueを返す。"""
        return self._poisoned

    def begin(self) -> None:
        """トランザクション開始"""
        if self._poisoned:
            raise RuntimeError("rollback不能になったUnitOfWorkは再利用できません")
        if self._in_transaction:
            raise RuntimeError("Transaction already in progress")
        if self._data_store is not None and self.supports_atomic_rollback:
            self._data_store.acquire_uow_transaction()
            self._transaction_lock_acquired = True
        try:
            snapshot = self._data_store.take_snapshot() if self._data_store is not None else None
        except BaseException as snapshot_error:
            try:
                self._release_transaction_lock()
            except BaseException as cleanup_error:
                self._poison_transaction_resource()
                raise InMemoryBeginCleanupError(
                    snapshot_error=snapshot_error,
                    cleanup_error=cleanup_error,
                ) from cleanup_error
            raise

        self._pending_operations = []
        self._pending_events = []
        self._pending_aggregates = {}
        self._committed = False
        self._committed_events = []
        self._snapshot = snapshot
        self._in_transaction = True

    def commit(self) -> None:
        """保留中の操作を実行して確定し、失敗したらロールバックする。"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        try:
            self.commit_transaction()
        except Exception:
            # コミット失敗時はロールバック
            if self._in_transaction:
                self.rollback()
            raise

    def commit_transaction(self) -> None:
        """同期配送や自動rollbackを行わず、永続化transactionだけを確定する。"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        self._execute_pending_operations()
        self._committed = True
        self._committed_events = self._pending_events.copy()
        self._in_transaction = False
        self._pending_operations.clear()
        self._pending_events.clear()
        self._pending_aggregates = {}
        self._snapshot = None
        try:
            self._release_transaction_lock()
        except BaseException as cleanup_error:
            self._poison_transaction_resource()
            raise InMemoryCommittedCleanupError(cleanup_error) from cleanup_error

    def _execute_pending_operations(self) -> None:
        """保留中の操作を順次実行する"""
        while self._pending_operations:
            # 操作の実行中にさらに操作が追加される可能性があるため
            operations = self._pending_operations.copy()
            self._pending_operations.clear()
            for operation in operations:
                operation()

    def execute_pending_operations(self) -> None:
        """保留中の操作を順次実行する。"""
        self._execute_pending_operations()

    def rollback(self) -> None:
        """ロールバック - 保留中の操作を破棄し、状態を復元"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")

        rollback_error: BaseException | None = None
        try:
            if self._data_store is not None and self._snapshot is not None:
                self._data_store.restore_snapshot(self._snapshot)
        except BaseException as error:
            rollback_error = error
            self._poison_transaction_resource()
        finally:
            self._pending_operations.clear()
            self._pending_events.clear()
            self._pending_aggregates = {}
            self._committed = False
            self._in_transaction = False
            self._snapshot = None
            try:
                self._release_transaction_lock()
            except BaseException as release_error:
                self._poison_transaction_resource()
                if rollback_error is None:
                    rollback_error = release_error
        if rollback_error is not None:
            raise rollback_error

    def _release_transaction_lock(self) -> None:
        if not self._transaction_lock_acquired:
            return
        try:
            self._data_store.release_uow_transaction()
        finally:
            self._transaction_lock_acquired = False

    def _poison_transaction_resource(self) -> None:
        self._poisoned = True
        if callable(getattr(self._data_store, "poison_uow_transactions", None)):
            self._data_store.poison_uow_transactions()

    def register_pending_aggregate(self, repo_key: str, entity_id: Any, aggregate: Any) -> None:
        """同一トランザクション内で find が未反映の集約を返せるよう、保留中の集約を登録する"""
        if not self._in_transaction:
            return
        self._pending_aggregates[(repo_key, entity_id)] = aggregate

    def get_pending_aggregate(self, repo_key: str, entity_id: Any) -> Any | None:
        """保留中の集約があれば返す（同一トランザクション内の一貫した find 用）"""
        if not self._in_transaction:
            return None
        return self._pending_aggregates.get((repo_key, entity_id))

    def add_operation(self, operation: Callable[[], object]) -> None:
        """保留中の操作を追加"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_operations.append(operation)

    def add_events(self, events: Sequence[DomainEvent]) -> None:
        """保留中のイベントを追加"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        self._pending_events.extend(events)

    def add_events_from_aggregate(self, aggregate: Any) -> None:
        """集約からイベントを収集し、add_events 経由で追加する（イベント収集 1 本化）"""
        if not self._in_transaction:
            raise RuntimeError("No transaction in progress")
        if hasattr(aggregate, "get_events") and hasattr(aggregate, "clear_events"):
            events = aggregate.get_events()
            if events:
                self._pending_events.extend(events)
            aggregate.clear_events()

    def get_pending_events(self) -> list[DomainEvent]:
        """保留中のイベントを取得（テスト用）"""
        return self._pending_events.copy()

    def has_pending_events(self) -> bool:
        """旧Unit of Work側に未回収イベントが残っていればTrueを返す。"""
        return bool(self._pending_events)

    def clear_pending_events(self) -> None:
        """保留中のイベントをクリア"""
        self._pending_events.clear()

    def is_in_transaction(self) -> bool:
        """トランザクション中かどうかを返す（テスト用）"""
        return self._in_transaction

    def get_committed_events(self) -> list[DomainEvent]:
        """コミット成功後に取り出し可能なイベントを返す。post-commit orchestration で使用。"""
        return self._committed_events.copy()

    def clear_committed_events(self) -> None:
        """コミット済みイベントをクリアする。post-commit orchestration 完了後に呼ぶ。"""
        self._committed_events.clear()

    def is_committed(self) -> bool:
        """コミット済みかどうかを返す（テスト用）"""
        return self._committed

    def __enter__(self) -> "InMemoryUnitOfWork":
        """コンテキストマネージャー開始"""
        self.begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """コンテキストマネージャー終了"""
        if exc_type is not None:
            # 例外が発生したらロールバック
            self.rollback()
        else:
            # 正常終了したらコミット
            self.commit()
