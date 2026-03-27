from __future__ import annotations

import sqlite3
from datetime import datetime

from ai_rpg_world.application.trade.services.recent_trade_query_service import (
    RecentTradeQueryService,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.recent_trade_read_model import (
    RecentTradeData,
    RecentTradeReadModel,
)
from ai_rpg_world.infrastructure.repository.sqlite_recent_trade_read_model_repository import (
    SqliteRecentTradeReadModelRepository,
)


def test_recent_trade_query_service_with_sqlite_repository() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteRecentTradeReadModelRepository.for_standalone_connection(conn)
    repo.save(
        RecentTradeReadModel(
            item_spec_id=ItemSpecId(1),
            item_name="鋼の剣",
            recent_trades=[
                RecentTradeData(
                    trade_id=101,
                    price=500,
                    traded_at=datetime(2026, 3, 28, 12, 0, 0),
                )
            ],
            last_updated=datetime(2026, 3, 28, 12, 0, 0),
        )
    )
    service = RecentTradeQueryService(repo)

    dto = service.get_recent_trades("鋼の剣")

    assert dto.item_name == "鋼の剣"
    assert len(dto.trades) == 1
    assert dto.trades[0].price == 500
