from __future__ import annotations

import sqlite3
from datetime import datetime

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.item_trade_statistics_read_model import (
    ItemTradeStatisticsReadModel,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_trade_statistics_read_model_repository import (
    SqliteItemTradeStatisticsReadModelRepository,
)


def _build_model(item_spec_id: int) -> ItemTradeStatisticsReadModel:
    return ItemTradeStatisticsReadModel(
        item_spec_id=ItemSpecId(item_spec_id),
        min_price=100,
        max_price=300,
        avg_price=200.0,
        median_price=190,
        total_trades=8,
        success_rate=0.75,
        last_updated=datetime(2026, 3, 28, 12, 0, 0),
    )


def test_save_and_find_statistics_round_trip() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteItemTradeStatisticsReadModelRepository.for_standalone_connection(conn)
    model = _build_model(3)

    repo.save(model)

    assert repo.find_statistics(ItemSpecId(3)) == model


def test_save_updates_existing_row() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteItemTradeStatisticsReadModelRepository.for_standalone_connection(conn)
    repo.save(_build_model(4))
    updated = ItemTradeStatisticsReadModel(
        item_spec_id=ItemSpecId(4),
        min_price=None,
        max_price=None,
        avg_price=None,
        median_price=None,
        total_trades=0,
        success_rate=0.0,
        last_updated=datetime(2026, 3, 28, 13, 0, 0),
    )

    repo.save(updated)

    assert repo.find_by_id(ItemSpecId(4)) == updated


def test_delete_removes_statistics() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteItemTradeStatisticsReadModelRepository.for_standalone_connection(conn)
    repo.save(_build_model(5))

    deleted = repo.delete(ItemSpecId(5))

    assert deleted is True
    assert repo.find_statistics(ItemSpecId(5)) is None
