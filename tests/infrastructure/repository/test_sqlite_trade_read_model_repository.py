"""
SqliteTradeReadModelRepository のテスト
"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.repository.trade_read_model_repository import TradeCursor
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)


def _make_trade(
    trade_id: int,
    seller_id: int,
    *,
    buyer_id: int | None = None,
    status: TradeStatus = TradeStatus.ACTIVE,
    created_at: datetime | None = None,
) -> TradeReadModel:
    base = created_at or datetime(2025, 1, 1, 12, 0, 0)
    return TradeReadModel.create_from_trade_and_item(
        trade_id=TradeId(trade_id),
        seller_id=PlayerId(seller_id),
        seller_name="seller",
        buyer_id=PlayerId(buyer_id) if buyer_id else None,
        buyer_name=None,
        item_instance_id=ItemInstanceId(trade_id),
        item_name=f"item-{trade_id}",
        item_quantity=1,
        item_type=ItemType.EQUIPMENT,
        item_rarity=Rarity.COMMON,
        item_description="d",
        item_equipment_type=EquipmentType.WEAPON,
        durability_current=10,
        durability_max=10,
        requested_gold=TradeRequestedGold(100),
        status=status,
        created_at=base,
    )


@pytest.fixture
def sqlite_repo() -> SqliteTradeReadModelRepository:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    repo = SqliteTradeReadModelRepository.for_standalone_connection(conn)
    yield repo
    conn.close()


class TestSqliteTradeReadModelRepository:
    def test_save_and_find_by_id(self, sqlite_repo: SqliteTradeReadModelRepository) -> None:
        t = _make_trade(1, seller_id=1)
        sqlite_repo.save(t)
        got = sqlite_repo.find_by_id(TradeId(1))
        assert got is not None
        assert got.trade_id == 1
        assert got.seller_id == 1

    def test_find_active_trades_as_seller_only_active_listings(self, sqlite_repo: SqliteTradeReadModelRepository) -> None:
        base = datetime(2025, 6, 1, 10, 0, 0)
        sqlite_repo.save(_make_trade(1, 1, status=TradeStatus.ACTIVE, created_at=base))
        sqlite_repo.save(
            _make_trade(2, 1, status=TradeStatus.COMPLETED, created_at=base + timedelta(hours=1))
        )
        sqlite_repo.save(_make_trade(3, 2, status=TradeStatus.ACTIVE, created_at=base + timedelta(hours=2)))

        trades, cursor = sqlite_repo.find_active_trades_as_seller(PlayerId(1), limit=20)
        ids = {x.trade_id for x in trades}
        assert ids == {1}

    def test_find_active_trades_as_seller_orders_newest_first(self, sqlite_repo: SqliteTradeReadModelRepository) -> None:
        base = datetime(2025, 6, 1, 10, 0, 0)
        sqlite_repo.save(_make_trade(1, 1, created_at=base))
        sqlite_repo.save(_make_trade(2, 1, created_at=base + timedelta(hours=1)))

        trades, _ = sqlite_repo.find_active_trades_as_seller(PlayerId(1), limit=10)
        assert [t.trade_id for t in trades] == [2, 1]

    def test_find_active_trades_as_seller_same_created_at_tie_break(self, sqlite_repo: SqliteTradeReadModelRepository) -> None:
        same = datetime(2025, 6, 1, 10, 0, 0)
        sqlite_repo.save(_make_trade(1, 1, created_at=same))
        sqlite_repo.save(_make_trade(11, 1, created_at=same))

        trades, _ = sqlite_repo.find_active_trades_as_seller(PlayerId(1), limit=10)
        assert [t.trade_id for t in trades] == [1, 11]

    def test_find_active_trades_as_seller_pagination_no_overlap(
        self, sqlite_repo: SqliteTradeReadModelRepository
    ) -> None:
        base = datetime(2025, 6, 1, 10, 0, 0)
        sqlite_repo.save(_make_trade(1, 1, created_at=base))
        sqlite_repo.save(_make_trade(2, 1, created_at=base + timedelta(hours=1)))

        first, next_c = sqlite_repo.find_active_trades_as_seller(PlayerId(1), limit=1)
        assert len(first) == 1
        assert next_c is not None
        second, final_c = sqlite_repo.find_active_trades_as_seller(PlayerId(1), limit=1, cursor=next_c)
        assert len(second) == 1
        assert first[0].trade_id != second[0].trade_id
        assert final_c is None

    def test_find_active_trades_as_seller_empty(self, sqlite_repo: SqliteTradeReadModelRepository) -> None:
        trades, c = sqlite_repo.find_active_trades_as_seller(PlayerId(99), limit=10)
        assert trades == []
        assert c is None

    def test_search_trades_respects_filter(self, sqlite_repo: SqliteTradeReadModelRepository) -> None:
        sqlite_repo.save(_make_trade(1, 1, created_at=datetime(2025, 1, 1)))
        sqlite_repo.save(_make_trade(2, 2, created_at=datetime(2025, 1, 2)))

        flt = TradeSearchFilter.by_item_name("item-1")
        rows, _ = sqlite_repo.search_trades(flt, limit=10)
        assert len(rows) == 1
        assert rows[0].trade_id == 1
