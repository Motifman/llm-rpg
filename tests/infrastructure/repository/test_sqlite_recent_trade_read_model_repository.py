from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.recent_trade_read_model import (
    RecentTradeData,
    RecentTradeReadModel,
)
from ai_rpg_world.infrastructure.repository.sqlite_recent_trade_read_model_repository import (
    SqliteRecentTradeReadModelRepository,
)


def _build_model(item_spec_id: int, item_name: str) -> RecentTradeReadModel:
    now = datetime(2026, 3, 28, 12, 0, 0)
    return RecentTradeReadModel(
        item_spec_id=ItemSpecId(item_spec_id),
        item_name=item_name,
        recent_trades=[
            RecentTradeData(trade_id=101, price=500, traded_at=now),
            RecentTradeData(trade_id=102, price=450, traded_at=now - timedelta(hours=1)),
        ],
        last_updated=now,
    )


def test_save_and_find_by_item_name_round_trip() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteRecentTradeReadModelRepository.for_standalone_connection(conn)
    model = _build_model(1, "鋼の剣")

    repo.save(model)

    loaded = repo.find_by_item_name("鋼の剣")

    assert loaded == model


def test_save_overwrites_entries() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteRecentTradeReadModelRepository.for_standalone_connection(conn)
    model = _build_model(1, "鋼の剣")
    repo.save(model)
    updated = RecentTradeReadModel(
        item_spec_id=model.item_spec_id,
        item_name=model.item_name,
        recent_trades=[model.recent_trades[0]],
        last_updated=model.last_updated,
    )

    repo.save(updated)

    loaded = repo.find_by_id(ItemSpecId(1))
    assert loaded == updated
    assert loaded is not None
    assert len(loaded.recent_trades) == 1


def test_delete_removes_model_and_entries() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteRecentTradeReadModelRepository.for_standalone_connection(conn)
    repo.save(_build_model(2, "魔法の杖"))

    deleted = repo.delete(ItemSpecId(2))

    assert deleted is True
    assert repo.find_by_id(ItemSpecId(2)) is None
