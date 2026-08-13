"""SQLite outboxが業務transactionと配送状態の境界を守ることを保証する。"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.common.transactional_outbox import StagedOutboxBatch
from ai_rpg_world.domain.trade.event.trade_event import TradeCancelledEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.infrastructure.events.sqlite_transactional_outbox import (
    SqliteTransactionalOutbox,
)
from ai_rpg_world.infrastructure.events.trade_event_json_serializer import (
    TradeEventJsonSerializer,
)
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
    SqliteUnitOfWorkTransactionAdapter,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _initialize(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        init_game_write_schema(connection)
        connection.commit()
    finally:
        connection.close()


def _event(event_id: int = 1) -> TradeCancelledEvent:
    return TradeCancelledEvent(
        event_id=event_id,
        occurred_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        aggregate_id=TradeId(7),
        aggregate_type="TradeAggregate",
    )


def _row(path: Path, event_id: int) -> sqlite3.Row | None:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(
            "SELECT * FROM command_event_outbox WHERE event_id = ?",
            (str(event_id),),
        ).fetchone()
    finally:
        connection.close()


def test_stage_commits_with_business_transaction_and_starts_pending(tmp_path: Path) -> None:
    """outbox行は業務transactionのcommitまで外部から見えず、未配送で確定する。"""
    database = tmp_path / "game.db"
    _initialize(database)
    unit_of_work = SqliteUnitOfWork(database=database)
    transaction = SqliteUnitOfWorkTransactionAdapter(unit_of_work)
    outbox = SqliteTransactionalOutbox(
        database,
        serializer=TradeEventJsonSerializer(),
        is_durable=lambda event: isinstance(event, TradeCancelledEvent),
    )
    event = _event()

    transaction.begin()
    batch = outbox.stage((event,), transaction)
    assert _row(database, event.event_id) is None
    transaction.commit()

    row = _row(database, event.event_id)
    assert batch == StagedOutboxBatch(event_ids=(str(event.event_id),))
    assert row is not None
    assert row["status"] == "pending"
    assert row["payload_schema_version"] == 1


def test_rollback_removes_staged_outbox_row(tmp_path: Path) -> None:
    """業務transactionをrollbackすると同時にoutbox行も残らない。"""
    database = tmp_path / "game.db"
    _initialize(database)
    unit_of_work = SqliteUnitOfWork(database=database)
    transaction = SqliteUnitOfWorkTransactionAdapter(unit_of_work)
    outbox = SqliteTransactionalOutbox(
        database,
        serializer=TradeEventJsonSerializer(),
        is_durable=lambda event: isinstance(event, TradeCancelledEvent),
    )

    transaction.begin()
    outbox.stage((_event(),), transaction)
    transaction.rollback()

    assert _row(database, 1) is None


def test_best_effort_only_event_is_not_staged(tmp_path: Path) -> None:
    """再送対象に登録されていないイベントはoutboxへ保存しない。"""
    database = tmp_path / "game.db"
    _initialize(database)
    unit_of_work = SqliteUnitOfWork(database=database)
    transaction = SqliteUnitOfWorkTransactionAdapter(unit_of_work)
    outbox = SqliteTransactionalOutbox(
        database,
        serializer=TradeEventJsonSerializer(),
        is_durable=lambda event: False,
    )

    transaction.begin()
    batch = outbox.stage((_event(),), transaction)
    transaction.commit()

    assert batch == StagedOutboxBatch(event_ids=())
    assert _row(database, 1) is None


def test_mark_delivered_updates_only_staged_rows(tmp_path: Path) -> None:
    """handoff成功後は対応する未配送行だけを配達済みに更新する。"""
    database = tmp_path / "game.db"
    _initialize(database)
    unit_of_work = SqliteUnitOfWork(database=database)
    transaction = SqliteUnitOfWorkTransactionAdapter(unit_of_work)
    outbox = SqliteTransactionalOutbox(
        database,
        serializer=TradeEventJsonSerializer(),
        is_durable=lambda event: isinstance(event, TradeCancelledEvent),
    )

    transaction.begin()
    batch = outbox.stage((_event(),), transaction)
    transaction.commit()
    outbox.mark_delivered(batch)

    row = _row(database, 1)
    assert row is not None
    assert row["status"] == "delivered"
    assert row["delivered_at"] is not None


def test_duplicate_event_id_creates_one_row(tmp_path: Path) -> None:
    """同じevent_idを再登録してもoutboxの再試行元は一件だけになる。"""
    database = tmp_path / "game.db"
    _initialize(database)
    outbox = SqliteTransactionalOutbox(
        database,
        serializer=TradeEventJsonSerializer(),
        is_durable=lambda event: isinstance(event, TradeCancelledEvent),
    )
    for _ in range(2):
        transaction = SqliteUnitOfWorkTransactionAdapter(
            SqliteUnitOfWork(database=database)
        )
        transaction.begin()
        outbox.stage((_event(),), transaction)
        transaction.commit()

    connection = sqlite3.connect(database)
    try:
        count = connection.execute(
            "SELECT COUNT(*) FROM command_event_outbox WHERE event_id = '1'"
        ).fetchone()
        assert count == (1,)
    finally:
        connection.close()


def test_stage_rejects_transaction_for_different_database(tmp_path: Path) -> None:
    """outboxと別DBのtransactionを誤配線すると書込み前に停止する。"""
    outbox_database = tmp_path / "outbox.db"
    transaction_database = tmp_path / "other.db"
    _initialize(outbox_database)
    _initialize(transaction_database)
    transaction = SqliteUnitOfWorkTransactionAdapter(
        SqliteUnitOfWork(database=transaction_database)
    )
    outbox = SqliteTransactionalOutbox(
        outbox_database,
        serializer=TradeEventJsonSerializer(),
        is_durable=lambda event: True,
    )

    transaction.begin()
    try:
        with pytest.raises(ValueError, match="同じDBパス"):
            outbox.stage((_event(),), transaction)
    finally:
        transaction.rollback()

    assert _row(outbox_database, 1) is None
    assert _row(transaction_database, 1) is None
