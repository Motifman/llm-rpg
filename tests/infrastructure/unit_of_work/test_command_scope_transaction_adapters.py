"""新TransactionPort adapterが永続化方式によらず同じ原子性を持つことを保証する。"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path
from typing import Protocol, Sequence

import pytest

from ai_rpg_world.application.common.command_scope import (
    AfterCommitHandoffPort,
    CommandContext,
    CommandScope,
    SyncDomainEventDispatcherPort,
    TransactionPort,
)
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent, DomainEvent
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    InMemoryUnitOfWorkTransactionAdapter,
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
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

    def take_snapshot(self) -> dict[str, str]:
        return copy.deepcopy(self.values)

    def restore_snapshot(self, snapshot: dict[str, str]) -> None:
        self.values = copy.deepcopy(snapshot)


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
