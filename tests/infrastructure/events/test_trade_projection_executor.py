"""取引投影executorの重複防止とtransaction原子性を保証する。"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

import pytest

from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import (
    TradeRequestedGold,
)
from ai_rpg_world.infrastructure.events.trade_projection_executor import (
    InMemoryTradeProjectionExecutor,
    SqliteTradeProjectionExecutor,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.trade_read_model_sqlite import (
    init_trade_read_model_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_migration import get_applied_version


def _read_model(trade_id: int) -> TradeReadModel:
    return TradeReadModel.create_from_trade_and_item(
        trade_id=TradeId(trade_id),
        seller_id=PlayerId(1),
        seller_name="Seller",
        buyer_id=None,
        buyer_name=None,
        item_instance_id=ItemInstanceId(10),
        item_name="Key",
        item_quantity=1,
        item_type=ItemType.CONSUMABLE,
        item_rarity=Rarity.COMMON,
        item_description="A key",
        item_equipment_type=None,
        durability_current=None,
        durability_max=None,
        requested_gold=TradeRequestedGold.of(50),
        status=TradeStatus.ACTIVE,
        created_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
    )


def test_in_memory_duplicate_event_does_not_run_projection_twice() -> None:
    """同じconsumerとeventの2回目はprojectionを呼ばずFalseを返す。"""
    repository = InMemoryTradeReadModelRepository()
    executor = InMemoryTradeProjectionExecutor(repository)
    calls: list[int] = []

    first = executor.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda repo: calls.append(1),
    )
    second = executor.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda repo: calls.append(2),
    )

    assert first is True
    assert second is False
    assert calls == [1]


def test_in_memory_same_event_is_processed_once_per_consumer() -> None:
    """同じevent_idでもconsumer IDが違えばそれぞれ一度処理する。"""
    executor = InMemoryTradeProjectionExecutor(InMemoryTradeReadModelRepository())
    calls: list[str] = []

    for consumer_id in ("first.v1", "second.v1"):
        assert executor.execute_once(
            consumer_id=consumer_id,
            event_id=100,
            projection=lambda repo, value=consumer_id: calls.append(value),
        )

    assert calls == ["first.v1", "second.v1"]


def test_in_memory_failed_projection_can_be_retried() -> None:
    """projection保存後の失敗時は更新を戻し、同じeventを再実行できる。"""
    repository = InMemoryTradeReadModelRepository()
    executor = InMemoryTradeProjectionExecutor(repository)

    def failing_projection(target) -> None:
        target.save(_read_model(99))
        raise RuntimeError("failed")

    with pytest.raises(RuntimeError, match="failed"):
        executor.execute_once(
            consumer_id="consumer.v1",
            event_id=100,
            projection=failing_projection,
        )

    assert repository.find_by_id(TradeId(99)) is None
    assert executor.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda target: target.save(_read_model(99)),
    )
    assert repository.find_by_id(TradeId(99)) is not None


def test_sqlite_projection_and_inbox_commit_together(tmp_path) -> None:
    """SQLiteではread model更新と処理済み行が同じtransactionで確定する。"""
    database = tmp_path / "read-model.db"
    executor = SqliteTradeProjectionExecutor(database)

    assert executor.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda repository: repository.save(_read_model(99)),
    )

    with sqlite3.connect(database) as connection:
        repository = SqliteTradeReadModelRepository.for_standalone_connection(connection)
        assert repository.find_by_id(TradeId(99)) is not None
        row = connection.execute(
            "SELECT consumer_id, event_id FROM event_consumer_inbox"
        ).fetchone()
        assert tuple(row) == ("consumer.v1", "100")


def test_sqlite_failure_rolls_back_projection_and_inbox(tmp_path) -> None:
    """SQLiteのprojection失敗時はread modelと処理済み行を両方残さない。"""
    database = tmp_path / "read-model.db"
    executor = SqliteTradeProjectionExecutor(database)

    def failing_projection(repository) -> None:
        repository.save(_read_model(99))
        raise RuntimeError("failed")

    with pytest.raises(RuntimeError, match="failed"):
        executor.execute_once(
            consumer_id="consumer.v1",
            event_id=100,
            projection=failing_projection,
        )

    with sqlite3.connect(database) as connection:
        repository = SqliteTradeReadModelRepository.for_standalone_connection(connection)
        assert repository.find_by_id(TradeId(99)) is None
        row = connection.execute(
            "SELECT COUNT(*) FROM event_consumer_inbox"
        ).fetchone()
        assert tuple(row) == (0,)
    assert executor.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda repo: repo.save(_read_model(99)),
    )


def test_sqlite_duplicate_event_skips_projection(tmp_path) -> None:
    """SQLite再起動後もinbox行を参照し、同じprojectionを再実行しない。"""
    database = tmp_path / "read-model.db"
    first = SqliteTradeProjectionExecutor(database)
    assert first.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda repo: repo.save(_read_model(99)),
    )
    calls: list[int] = []

    second = SqliteTradeProjectionExecutor(database)
    result = second.execute_once(
        consumer_id="consumer.v1",
        event_id=100,
        projection=lambda repo: calls.append(1),
    )

    assert result is False
    assert calls == []


def test_trade_read_model_v1_migrates_without_losing_projection(tmp_path) -> None:
    """v1のread modelを保持したままconsumer inboxを追加してv2へ移行する。"""
    database = tmp_path / "read-model.db"
    with sqlite3.connect(database) as connection:
        init_trade_read_model_schema(connection)
        repository = SqliteTradeReadModelRepository.for_standalone_connection(connection)
        repository.save(_read_model(99))
        connection.execute("DROP TABLE event_consumer_inbox")
        connection.execute(
            "UPDATE schema_migrations SET version = 1 WHERE namespace = ?",
            ("trade_read_model",),
        )
        connection.commit()

        init_trade_read_model_schema(connection)

        assert repository.find_by_id(TradeId(99)) is not None
        assert get_applied_version(connection, "trade_read_model") == 2
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            ("event_consumer_inbox",),
        ).fetchone() is not None


@pytest.mark.parametrize(
    ("consumer_id", "event_id"),
    (
        ("", 1),
        ("   ", 1),
        (" consumer.v1", 1),
        (1, 1),
        ("consumer.v1", True),
        ("consumer.v1", 0),
    ),
)
def test_invalid_consumer_identity_is_rejected_before_projection(
    consumer_id: object,
    event_id: object,
) -> None:
    """不正なconsumer IDまたはevent IDをprojection実行前に拒否する。"""
    calls: list[int] = []
    executor = InMemoryTradeProjectionExecutor(InMemoryTradeReadModelRepository())

    with pytest.raises(ValueError):
        executor.execute_once(
            consumer_id=consumer_id,  # type: ignore[arg-type]
            event_id=event_id,  # type: ignore[arg-type]
            projection=lambda repo: calls.append(1),
        )

    assert calls == []
