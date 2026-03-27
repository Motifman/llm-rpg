"""In-memory と SQLite の TradeReadModel カーソルストリーム順序が一致することを検証する。"""

import sqlite3
from datetime import datetime

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import (
    InMemoryTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)


def _make_trade(
    trade_id: int,
    seller_id: int,
    *,
    status: TradeStatus = TradeStatus.ACTIVE,
    created_at: datetime | None = None,
) -> TradeReadModel:
    base = created_at or datetime(2025, 1, 1, 12, 0, 0)
    return TradeReadModel.create_from_trade_and_item(
        trade_id=TradeId(trade_id),
        seller_id=PlayerId(seller_id),
        seller_name="seller",
        buyer_id=None,
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


class TestTradeReadModelRepositoryParity:
    def test_find_active_trades_as_seller_same_created_at_order_matches_sqlite(self) -> None:
        same = datetime(2025, 6, 1, 10, 0, 0)
        mem = InMemoryTradeReadModelRepository()
        mem.clear()
        mem.save(_make_trade(1, 1, created_at=same))
        mem.save(_make_trade(11, 1, created_at=same))

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        sql = SqliteTradeReadModelRepository.for_standalone_connection(conn)
        sql.save(_make_trade(1, 1, created_at=same))
        sql.save(_make_trade(11, 1, created_at=same))

        m_rows, _ = mem.find_active_trades_as_seller(PlayerId(1), limit=10)
        s_rows, _ = sql.find_active_trades_as_seller(PlayerId(1), limit=10)
        assert [t.trade_id for t in m_rows] == [t.trade_id for t in s_rows] == [1, 11]

        m1, mc = mem.find_active_trades_as_seller(PlayerId(1), limit=1)
        s1, sc = sql.find_active_trades_as_seller(PlayerId(1), limit=1)
        assert m1[0].trade_id == s1[0].trade_id == 1
        assert mc is not None and sc is not None

        m2, m_end = mem.find_active_trades_as_seller(PlayerId(1), limit=1, cursor=mc)
        s2, s_end = sql.find_active_trades_as_seller(PlayerId(1), limit=1, cursor=sc)
        assert m2[0].trade_id == s2[0].trade_id == 11
        assert m_end is None and s_end is None
        conn.close()
