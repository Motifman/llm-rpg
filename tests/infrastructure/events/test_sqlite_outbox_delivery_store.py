"""SqliteOutboxDeliveryStoreのpending取得と試行状態の永続化を保証する。"""

from __future__ import annotations

import sqlite3

import pytest

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
    """handlerの一時失敗はpendingを維持し、次回試行の判断材料を保存する。"""
    database = tmp_path / "game.db"
    _initialize(database)
    _insert(database, event_id="1", created_at="2026-08-14T00:00:00+00:00")

    SqliteOutboxDeliveryStore(database).record_retryable_failure(
        "1", RuntimeError("temporary")
    )

    row = _row(database, "1")
    assert row["status"] == "pending"
    assert row["attempt_count"] == 1
    assert row["last_attempted_at"] is not None
    assert row["last_error"] == "RuntimeError: temporary"


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
