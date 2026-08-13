"""新TransactionPort adapterが永続化方式によらず同じ原子性を持つことを保証する。"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path
from typing import Protocol, Sequence

import pytest

from ai_rpg_world.application.common.command_scope import (
    AfterCommitHandoffPort,
    CommandCompletion,
    CommandContext,
    CommandScope,
    SyncDomainEventDispatcherPort,
    TransactionPort,
)
from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryBeginCleanupError,
    InMemoryUnitOfWork,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWork,
)


class _NoOpDispatcher(SyncDomainEventDispatcherPort):
    def dispatch(self, event: DomainEvent, context: CommandContext) -> None:
        pass


class _NoOpHandoff(AfterCommitHandoffPort):
    def handoff(self, events: Sequence[DomainEvent]) -> None:
        pass


class _AtomicityHarness(Protocol):
    adapter: TransactionPort

    def write(self, key: str, value: str) -> None: ...

    def read_committed(self, key: str) -> str | None: ...

    def add_legacy_event(self, event: DomainEvent) -> None: ...


class _SnapshotDataStore:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.locked = False
        self.poisoned = False
        self.release_error: BaseException | None = None

    def take_snapshot(self) -> dict[str, str]:
        return copy.deepcopy(self.values)

    def restore_snapshot(self, snapshot: dict[str, str]) -> None:
        self.values = copy.deepcopy(snapshot)

    def acquire_uow_transaction(self) -> None:
        if self.poisoned:
            raise RuntimeError("poisoned")
        if self.locked:
            raise RuntimeError("already locked")
        self.locked = True

    def release_uow_transaction(self) -> None:
        if self.release_error is not None:
            raise self.release_error
        self.locked = False

    def poison_uow_transactions(self) -> None:
        self.poisoned = True


class _InMemoryHarness:
    def __init__(self) -> None:
        self.store = _SnapshotDataStore()
        self.uow = InMemoryUnitOfWork(data_store=self.store)
        self.adapter = InMemoryUnitOfWorkTransactionAdapter(self.uow)

    def write(self, key: str, value: str) -> None:
        self.uow.add_operation(lambda: self.store.values.__setitem__(key, value))

    def read_committed(self, key: str) -> str | None:
        return self.store.values.get(key)

    def add_legacy_event(self, event: DomainEvent) -> None:
        self.uow.add_events([event])


class _SqliteHarness:
    def __init__(self, database: Path) -> None:
        self.database = database
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "CREATE TABLE values_for_test (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.commit()
        finally:
            connection.close()
        self.uow = SqliteUnitOfWork(database)
        self.adapter = SqliteUnitOfWorkTransactionAdapter(self.uow)

    def write(self, key: str, value: str) -> None:
        self.uow.connection.execute(
            "INSERT INTO values_for_test (key, value) VALUES (?, ?)",
            (key, value),
        )

    def read_committed(self, key: str) -> str | None:
        connection = sqlite3.connect(self.database)
        try:
            row = connection.execute(
                "SELECT value FROM values_for_test WHERE key = ?", (key,)
            ).fetchone()
            return None if row is None else str(row[0])
        finally:
            connection.close()

    def add_legacy_event(self, event: DomainEvent) -> None:
        self.uow.add_events([event])


@pytest.fixture(params=["in_memory", "sqlite"])
def harness(request: pytest.FixtureRequest, tmp_path: Path) -> _AtomicityHarness:
    if request.param == "in_memory":
        return _InMemoryHarness()
    return _SqliteHarness(tmp_path / "command_scope.db")


def _scope(adapter: TransactionPort) -> CommandScope:
    return CommandScope(
        adapter,
        sync_dispatcher=_NoOpDispatcher(),
        after_commit_handoff=_NoOpHandoff(),
    )


class TestCommandScopeTransactionAdapterContract:
    """両adapterへ同じcommit・rollback・transaction外拒否契約を適用する。"""

    def test_two_writes_commit_together(self, harness: _AtomicityHarness) -> None:
        """正常commandでは二つの書込みが同じtransactionで確定する。"""
        with _scope(harness.adapter):
            harness.write("first", "a")
            harness.write("second", "b")

        assert harness.read_committed("first") == "a"
        assert harness.read_committed("second") == "b"

    def test_command_error_rolls_back_both_writes(
        self, harness: _AtomicityHarness
    ) -> None:
        """二つ目の処理で失敗すると一つ目を含む全書込みを破棄する。"""
        with pytest.raises(RuntimeError, match="abort"):
            with _scope(harness.adapter):
                harness.write("first", "a")
                harness.write("second", "b")
                raise RuntimeError("abort")

        assert harness.read_committed("first") is None
        assert harness.read_committed("second") is None

    def test_adapter_reports_active_state_only_inside_scope(
        self, harness: _AtomicityHarness
    ) -> None:
        """adapterのis_activeは開始前と終了後にFalse、command内だけTrueになる。"""
        assert harness.adapter.is_active is False
        with _scope(harness.adapter):
            assert harness.adapter.is_active is True
        assert harness.adapter.is_active is False

    def test_write_outside_scope_is_rejected(self, harness: _AtomicityHarness) -> None:
        """transaction外の書込みは即時反映せず明示的に拒否する。"""
        with pytest.raises(RuntimeError):
            harness.write("outside", "value")

        assert harness.read_committed("outside") is None

    def test_legacy_pending_event_rolls_back_instead_of_being_lost(
        self, harness: _AtomicityHarness
    ) -> None:
        """旧UoWへイベントを残したcommandはcommitせずCommandContext移行を要求する。"""
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="test")

        with pytest.raises(RuntimeError, match="CommandContext"):
            with _scope(harness.adapter):
                harness.add_legacy_event(event)

        assert harness.adapter.is_active is False

    def test_operation_generated_legacy_event_is_detected_before_commit(
        self, harness: _AtomicityHarness
    ) -> None:
        """保留書込みの実行中に旧UoWへ追加されたイベントもcommit前に拒否する。"""
        if not isinstance(harness, _InMemoryHarness):
            pytest.skip("保留operationを持つインメモリadapter固有の契約")
        event = BaseDomainEvent.create(aggregate_id=1, aggregate_type="test")

        with pytest.raises(RuntimeError, match="CommandContext"):
            with _scope(harness.adapter):
                harness.uow.add_operation(lambda: harness.uow.add_events([event]))

        assert harness.adapter.is_active is False
        assert harness.uow.get_committed_events() == []


class TestTransactionOnlyCommit:
    """transaction専用commitが失敗時のrollbackをCommandScopeへ委ねる。"""

    def test_in_memory_commit_failure_leaves_transaction_active(self) -> None:
        """保留操作の失敗後もactiveを保ち、呼出し側がrollbackできる。"""
        store = _SnapshotDataStore()
        uow = InMemoryUnitOfWork(data_store=store)
        adapter = InMemoryUnitOfWorkTransactionAdapter(uow)
        adapter.begin()

        def fail_after_write() -> None:
            store.values["leaked"] = "value"
            raise RuntimeError("commit failed")

        uow.add_operation(fail_after_write)
        with pytest.raises(RuntimeError, match="commit failed"):
            adapter.commit()

        assert adapter.is_active is True
        adapter.rollback()
        assert store.values == {}

    def test_sqlite_commit_failure_leaves_transaction_active(
        self, tmp_path: Path
    ) -> None:
        """SQLite commit制約違反後もactiveを保ち、呼出し側がrollbackできる。"""
        database = tmp_path / "deferred_constraint.db"
        bootstrap = sqlite3.connect(database)
        try:
            bootstrap.execute("PRAGMA foreign_keys = ON")
            bootstrap.executescript(
                """
                CREATE TABLE parent (id INTEGER PRIMARY KEY);
                CREATE TABLE child (
                    parent_id INTEGER,
                    FOREIGN KEY(parent_id) REFERENCES parent(id)
                        DEFERRABLE INITIALLY DEFERRED
                );
                """
            )
            bootstrap.commit()
        finally:
            bootstrap.close()

        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            uow = SqliteUnitOfWork(connection=connection)
            adapter = SqliteUnitOfWorkTransactionAdapter(uow)
            adapter.begin()
            uow.connection.execute("INSERT INTO child (parent_id) VALUES (999)")

            with pytest.raises(sqlite3.IntegrityError):
                adapter.commit()

            assert adapter.is_active is True
            adapter.rollback()
            assert adapter.is_active is False
        finally:
            connection.close()

    def test_in_memory_adapter_rejects_legacy_sync_dispatcher(self) -> None:
        """旧同期dispatcherを持つインメモリUoWは二重処理を避けて拒否する。"""
        uow = InMemoryUnitOfWork(
            data_store=_SnapshotDataStore(),
            sync_event_dispatcher=object(),
        )
        with pytest.raises(ValueError, match="sync_event_dispatcher"):
            InMemoryUnitOfWorkTransactionAdapter(uow)

    def test_sqlite_adapter_rejects_legacy_sync_dispatcher(self) -> None:
        """旧同期dispatcherを持つSQLite UoWは二重処理を避けて拒否する。"""
        connection = sqlite3.connect(":memory:")
        try:
            uow = SqliteUnitOfWork(
                connection=connection,
                sync_event_dispatcher=object(),
            )
            with pytest.raises(ValueError, match="sync_event_dispatcher"):
                SqliteUnitOfWorkTransactionAdapter(uow)
        finally:
            connection.close()

    def test_in_memory_adapter_requires_rollback_snapshot_source(self) -> None:
        """snapshot元なしのインメモリUoWは部分適用を戻せないため拒否する。"""
        with pytest.raises(ValueError, match="data_store"):
            InMemoryUnitOfWorkTransactionAdapter(InMemoryUnitOfWork())


class TestInMemoryFailureIsolation:
    """開始・復元失敗と同時transactionが共有storeを壊さないことを保証する。"""

    def test_snapshot_failure_leaves_uow_inactive_and_releases_store(self) -> None:
        """snapshot取得失敗時はtransactionを開始済みにせず排他も解除する。"""
        store = _SnapshotDataStore()
        uow = InMemoryUnitOfWork(data_store=store)
        adapter = InMemoryUnitOfWorkTransactionAdapter(uow)

        def fail_snapshot() -> dict[str, str]:
            raise RuntimeError("snapshot failed")

        store.take_snapshot = fail_snapshot  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="snapshot failed"):
            adapter.begin()

        assert adapter.is_active is False
        assert store.locked is False

    def test_snapshot_and_release_errors_are_preserved_and_poison_store(self) -> None:
        """snapshot取得と排他解放が共に失敗すると両例外を保持してstoreを隔離する。"""
        store = _SnapshotDataStore()
        snapshot_error = RuntimeError("snapshot failed")
        release_error = RuntimeError("release failed")
        store.release_error = release_error
        uow = InMemoryUnitOfWork(data_store=store)
        adapter = InMemoryUnitOfWorkTransactionAdapter(uow)

        def fail_snapshot() -> dict[str, str]:
            raise snapshot_error

        store.take_snapshot = fail_snapshot  # type: ignore[method-assign]
        with pytest.raises(InMemoryBeginCleanupError) as caught:
            adapter.begin()

        assert caught.value.snapshot_error is snapshot_error
        assert caught.value.cleanup_error is release_error
        assert adapter.is_active is False
        assert uow.is_poisoned is True
        assert store.poisoned is True
        with pytest.raises(RuntimeError, match="再利用"):
            adapter.begin()

    def test_restore_failure_poisoned_uow_cannot_commit_or_restart(self) -> None:
        """snapshot復元失敗後は保留操作を破棄し、同じUoWを再利用させない。"""
        store = _SnapshotDataStore()
        uow = InMemoryUnitOfWork(data_store=store)
        adapter = InMemoryUnitOfWorkTransactionAdapter(uow)
        adapter.begin()
        uow.add_operation(lambda: store.values.__setitem__("leaked", "value"))

        def fail_restore(snapshot: dict[str, str]) -> None:
            raise RuntimeError("restore failed")

        store.restore_snapshot = fail_restore  # type: ignore[method-assign]
        with pytest.raises(RuntimeError, match="restore failed"):
            adapter.rollback()

        assert adapter.is_active is False
        assert uow.is_poisoned is True
        assert store.poisoned is True
        assert store.locked is False
        with pytest.raises(RuntimeError, match="再利用"):
            adapter.begin()
        with pytest.raises(RuntimeError, match="No transaction"):
            adapter.commit()

    def test_second_uow_cannot_snapshot_same_store_concurrently(self) -> None:
        """同じstoreの古いsnapshotを戻して他commandのcommitを消す同時実行を拒否する。"""
        store = _SnapshotDataStore()
        first = InMemoryUnitOfWorkTransactionAdapter(
            InMemoryUnitOfWork(data_store=store)
        )
        second = InMemoryUnitOfWorkTransactionAdapter(
            InMemoryUnitOfWork(data_store=store)
        )
        first.begin()

        with pytest.raises(RuntimeError, match="already locked"):
            second.begin()

        assert second.is_active is False
        first.rollback()


class _FailingSqliteConnection:
    """commit/rollback/closeの失敗境界を再現する最小connection fake。"""

    def __init__(
        self,
        *,
        rollback_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.row_factory: object | None = None
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.database_active = False
        self.committed = False
        self.rollback_count = 0

    def execute(self, sql: str) -> None:
        if sql == "BEGIN":
            if self.database_active:
                raise RuntimeError("database transaction already active")
            self.database_active = True

    def commit(self) -> None:
        self.committed = True
        self.database_active = False

    def rollback(self) -> None:
        self.rollback_count += 1
        if self.rollback_error is not None:
            raise self.rollback_error
        self.database_active = False

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error


class TestSqliteFailureIsolation:
    """SQLiteの確定後cleanupとrollback不能を別の結果として扱うことを保証する。"""

    def test_commit_cleanup_failure_is_reported_as_post_commit_without_rollback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """durable commit後のclose失敗はcommit済み後処理例外となりrollbackしない。"""
        close_error = RuntimeError("close failed")
        connection = _FailingSqliteConnection(close_error=close_error)
        monkeypatch.setattr(sqlite3, "connect", lambda path: connection)
        uow = SqliteUnitOfWork(database=":memory:")
        scope = _scope(SqliteUnitOfWorkTransactionAdapter(uow))

        with pytest.raises(CommandPostCommitException) as caught:
            with scope:
                pass

        assert caught.value.cleanup_error is close_error
        assert caught.value.handoff_error is None
        assert connection.committed is True
        assert connection.rollback_count == 0
        assert scope.completion is CommandCompletion.COMMITTED
        assert uow.is_poisoned is True

    def test_rollback_failure_poisoned_uow_cannot_restart(self) -> None:
        """DB側rollback失敗後はadapter表示をinactiveにして同じUoWの再利用を拒否する。"""
        rollback_error = RuntimeError("rollback failed")
        connection = _FailingSqliteConnection(rollback_error=rollback_error)
        uow = SqliteUnitOfWork(connection=connection)  # type: ignore[arg-type]
        adapter = SqliteUnitOfWorkTransactionAdapter(uow)
        adapter.begin()

        with pytest.raises(RuntimeError, match="rollback failed"):
            adapter.rollback()

        assert adapter.is_active is False
        assert connection.database_active is True
        assert uow.is_poisoned is True
        with pytest.raises(RuntimeError, match="再利用"):
            adapter.begin()

    def test_commit_cleanup_keyboard_interrupt_keeps_control_flow_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """durable commit後のclose中断はscopeを閉じた後もKeyboardInterruptとして伝播する。"""
        interrupt = KeyboardInterrupt()
        connection = _FailingSqliteConnection(close_error=interrupt)
        monkeypatch.setattr(sqlite3, "connect", lambda path: connection)
        uow = SqliteUnitOfWork(database=":memory:")
        scope = _scope(SqliteUnitOfWorkTransactionAdapter(uow))

        with pytest.raises(KeyboardInterrupt) as caught:
            with scope:
                pass

        assert caught.value is interrupt
        assert connection.committed is True
        assert connection.rollback_count == 0
        assert scope.completion is CommandCompletion.COMMITTED
        assert uow.is_poisoned is True

    def test_cleanup_interrupt_preserves_handoff_error_as_cause(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """cleanup中断とhandoff失敗が重なると中断を主例外、handoffを原因として保持する。"""
        interrupt = KeyboardInterrupt()
        handoff_error = RuntimeError("handoff failed")
        connection = _FailingSqliteConnection(close_error=interrupt)
        monkeypatch.setattr(sqlite3, "connect", lambda path: connection)
        uow = SqliteUnitOfWork(database=":memory:")

        class _FailingHandoff:
            def handoff(self, events: Sequence[DomainEvent]) -> None:
                raise handoff_error

        scope = CommandScope(
            SqliteUnitOfWorkTransactionAdapter(uow),
            sync_dispatcher=_NoOpDispatcher(),
            after_commit_handoff=_FailingHandoff(),
        )

        with pytest.raises(KeyboardInterrupt) as caught:
            with scope:
                pass

        assert caught.value is interrupt
        assert caught.value.__cause__ is handoff_error
        assert scope.completion is CommandCompletion.COMMITTED
