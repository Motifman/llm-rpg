"""SqliteOutboxDeliveryStoreのpending取得と試行状態の永続化を保証する。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from ai_rpg_world.application.common.outbox_worker import OutboxRetryPolicy
from ai_rpg_world.infrastructure.events.sqlite_outbox_delivery_store import (
    SqliteOutboxDeliveryStore,
)
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)


def _initialize(database) -> None:
    connection = sqlite3.connect(database)
    init_game_write_schema(connection)
    connection.commit()
    connection.close()


def _insert(
    database,
    *,
    event_id: str,
    created_at: str,
    status: str = "pending",
) -> None:
    connection = sqlite3.connect(database)
    connection.execute(
        """
        INSERT INTO command_event_outbox (
            event_id, event_type, payload, payload_schema_version,
            status, created_at, delivered_at
        ) VALUES (?, 'demo:Event', X'7B7D', 1, ?, ?, NULL)
        """,
        (event_id, status, created_at),
    )
    connection.commit()
    connection.close()


def _row(database, event_id: str) -> sqlite3.Row:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM command_event_outbox WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        assert row is not None
        return row
    finally:
        connection.close()


def test_fetch_pending_uses_registration_order_limit_and_excludes_final_rows(tmp_path) -> None:
    """pending行だけをoutbox登録順でlimit件取得する。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:01+00:00")
    _insert(database, event_id="2", created_at="2026-08-14T00:00:02+00:00")
    _insert(database, event_id="3", created_at="2026-08-14T00:00:00+00:00")
    _insert(
        database,
        event_id="4",
        created_at="2026-08-14T00:00:00+00:00",
        status="delivered",
    )
    _insert(
        database,
        event_id="5",
        created_at="2026-08-14T00:00:00+00:00",
        status="rejected",
    )

    messages = SqliteOutboxDeliveryStore(database).fetch_pending(limit=2)

    assert [message.event_id for message in messages] == ["1", "2"]
    assert messages[0].payload == b"{}"


def test_successful_delivery_records_one_attempt_and_completion_time(tmp_path) -> None:
    """handler成功時は試行回数を増やし、配達済み時刻を保存する。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:00+00:00")

    SqliteOutboxDeliveryStore(database).mark_delivered("1")

    row = _row(database, "1")
    assert row["status"] == "delivered"
    assert row["attempt_count"] == 1
    assert row["delivered_at"] is not None
    assert row["last_error"] is None


def test_retryable_failure_remains_pending_and_records_error(tmp_path) -> None:
    """handlerの一時失敗はpendingを維持し、指数的な次回試行時刻を保存する。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:00+00:00")
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    store = SqliteOutboxDeliveryStore(
        database,
        retry_policy=OutboxRetryPolicy(
            max_attempts=4,
            initial_delay_seconds=2,
            max_delay_seconds=10,
        ),
        now_provider=lambda: now,
    )

    first = store.record_retryable_failure("1", RuntimeError("temporary"))
    now += timedelta(seconds=2)
    second = store.record_retryable_failure("1", RuntimeError("temporary again"))

    row = _row(database, "1")
    assert row["status"] == "pending"
    assert row["attempt_count"] == 2
    assert row["last_attempted_at"] is not None
    assert row["last_error"] == "RuntimeError: temporary again"
    assert first.next_attempt_at == datetime(
        2026, 8, 14, 0, 0, 2, tzinfo=timezone.utc
    )
    assert second.next_attempt_at == datetime(
        2026, 8, 14, 0, 0, 6, tzinfo=timezone.utc
    )
    assert row["next_attempt_at"] == second.next_attempt_at.isoformat()


def test_waiting_oldest_message_blocks_later_ready_messages(tmp_path) -> None:
    """最古のpending行が待機中なら、後続行を追い越して取得しない。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:00+00:00")
    _insert(database, event_id="2", created_at="2026-08-14T00:00:01+00:00")
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    store = SqliteOutboxDeliveryStore(
        database,
        retry_policy=OutboxRetryPolicy(initial_delay_seconds=5),
        now_provider=lambda: now,
    )
    store.record_retryable_failure("1", RuntimeError("temporary"))

    assert store.fetch_pending(limit=10) == ()

    now += timedelta(seconds=5)
    assert [message.event_id for message in store.fetch_pending(limit=10)] == ["1", "2"]


def test_retry_limit_moves_message_to_dead_letter(tmp_path) -> None:
    """最大試行回数の失敗で行をdead letterへ隔離し、後続取得を可能にする。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:00+00:00")
    _insert(database, event_id="2", created_at="2026-08-14T00:00:01+00:00")
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    store = SqliteOutboxDeliveryStore(
        database,
        retry_policy=OutboxRetryPolicy(max_attempts=2),
        now_provider=lambda: now,
    )

    first = store.record_retryable_failure("1", RuntimeError("first"))
    now = first.next_attempt_at
    assert now is not None
    final = store.record_retryable_failure("1", RuntimeError("final"))

    row = _row(database, "1")
    assert final.dead_lettered is True
    assert final.next_attempt_at is None
    assert row["status"] == "dead_letter"
    assert row["attempt_count"] == 2
    assert row["dead_lettered_at"] == now.isoformat()
    assert row["next_attempt_at"] is None
    assert [message.event_id for message in store.fetch_pending(limit=10)] == ["2"]


def test_permanent_failure_is_rejected_from_normal_polling(tmp_path) -> None:
    """復元不能行はrejectedへ隔離し、次回のpending取得に含めない。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:00+00:00")
    store = SqliteOutboxDeliveryStore(database)

    store.mark_rejected("1", ValueError("invalid payload"))

    row = _row(database, "1")
    assert row["status"] == "rejected"
    assert row["rejected_at"] is not None
    assert row["last_error"] == "ValueError: invalid payload"
    assert store.fetch_pending(limit=10) == ()


def test_final_or_unknown_row_cannot_be_acknowledged_again(tmp_path) -> None:
    """pendingでない行や存在しない行の更新を成功扱いしない。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(
        database,
        event_id="1",
        created_at="2026-08-14T00:00:00+00:00",
        status="delivered",
    )
    store = SqliteOutboxDeliveryStore(database)

    with pytest.raises(RuntimeError, match="event_id=1"):
        store.mark_delivered("1")
    with pytest.raises(RuntimeError, match="event_id=missing"):
        store.mark_delivered("missing")
