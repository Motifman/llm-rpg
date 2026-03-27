"""
Personal / TradeDetail / GlobalMarket ReadModel の in-memory と SQLite の parity。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import pytest

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.global_market_listing_read_model import (
    GlobalMarketListingReadModel,
)
from ai_rpg_world.domain.trade.read_model.personal_trade_listing_read_model import (
    PersonalTradeListingReadModel,
)
from ai_rpg_world.domain.trade.read_model.trade_detail_read_model import TradeDetailReadModel
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.infrastructure.repository.in_memory_global_market_listing_read_model_repository import (
    InMemoryGlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_personal_trade_listing_read_model_repository import (
    InMemoryPersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.global_market_listing_read_model_repository_factory import (
    create_global_market_listing_read_model_repository_from_env,
)
from ai_rpg_world.infrastructure.repository.in_memory_trade_detail_read_model_repository import (
    InMemoryTradeDetailReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.personal_trade_listing_read_model_repository_factory import (
    create_personal_trade_listing_read_model_repository_from_env,
    create_personal_trade_listing_read_model_repository_from_path,
)
from ai_rpg_world.infrastructure.repository.sqlite_global_market_listing_read_model_repository import (
    SqliteGlobalMarketListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_personal_trade_listing_read_model_repository import (
    SqlitePersonalTradeListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_detail_read_model_repository import (
    SqliteTradeDetailReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.trade_detail_read_model_repository_factory import (
    create_trade_detail_read_model_repository_from_env,
)
T0 = datetime(2026, 3, 10, 10, 0, 0)


def _personal(
    trade_id: int,
    recipient: int,
    *,
    created: datetime = T0,
    name: str = "item",
    gold: int = 100,
) -> PersonalTradeListingReadModel:
    return PersonalTradeListingReadModel.create_from_trade_data(
        trade_id=TradeId(trade_id),
        item_spec_id=ItemSpecId(trade_id),
        item_instance_id=ItemInstanceId(trade_id),
        recipient_player_id=PlayerId(recipient),
        item_name=name,
        item_quantity=1,
        item_type=ItemType.EQUIPMENT,
        item_rarity=Rarity.COMMON,
        item_equipment_type=EquipmentType.WEAPON,
        durability_current=10,
        durability_max=10,
        requested_gold=gold,
        seller_name="s",
        created_at=created,
    )


def _detail(trade_id: int, *, status: TradeStatus = TradeStatus.ACTIVE) -> TradeDetailReadModel:
    return TradeDetailReadModel.create_from_trade_data(
        trade_id=TradeId(trade_id),
        item_spec_id=ItemSpecId(trade_id),
        item_instance_id=ItemInstanceId(trade_id),
        item_name=f"n-{trade_id}",
        item_quantity=1,
        item_type=ItemType.CONSUMABLE,
        item_rarity=Rarity.UNCOMMON,
        item_description="d",
        item_equipment_type=None,
        durability_current=None,
        durability_max=None,
        requested_gold=50,
        seller_name="a",
        buyer_name=None,
        status=status.value,
    )


def _global(
    trade_id: int,
    *,
    created: datetime = T0,
    name: str = "g",
    gold: int = 200,
    status: TradeStatus = TradeStatus.ACTIVE,
) -> GlobalMarketListingReadModel:
    return GlobalMarketListingReadModel.create_from_trade_data(
        trade_id=TradeId(trade_id),
        item_spec_id=ItemSpecId(trade_id),
        item_instance_id=ItemInstanceId(trade_id),
        item_name=name,
        item_quantity=1,
        item_type=ItemType.MATERIAL,
        item_rarity=Rarity.RARE,
        item_equipment_type=None,
        status=status,
        created_at=created,
        durability_current=None,
        durability_max=None,
        requested_gold=gold,
    )


def _assert_personal_equal(a: PersonalTradeListingReadModel, b: PersonalTradeListingReadModel) -> None:
    assert a.trade_id == b.trade_id
    assert a.recipient_player_id == b.recipient_player_id
    assert a.item_name == b.item_name
    assert a.created_at == b.created_at
    assert a.requested_gold == b.requested_gold


def _assert_detail_equal(a: TradeDetailReadModel, b: TradeDetailReadModel) -> None:
    assert a.trade_id == b.trade_id
    assert a.status == b.status
    assert a.item_name == b.item_name


def _assert_global_equal(a: GlobalMarketListingReadModel, b: GlobalMarketListingReadModel) -> None:
    assert a.trade_id == b.trade_id
    assert a.status == b.status
    assert a.created_at == b.created_at
    assert a.requested_gold == b.requested_gold


class TestPersonalTradeListingParity:
    def test_find_for_player_order_and_cursor_parity(self, tmp_path) -> None:
        mem = InMemoryPersonalTradeListingReadModelRepository()
        mem.clear()
        db = tmp_path / "g.db"
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        sql = SqlitePersonalTradeListingReadModelRepository.for_standalone_connection(conn)

        p1 = PlayerId(1)
        models = [
            _personal(1, 1, created=T0 + timedelta(hours=2)),
            _personal(2, 1, created=T0 + timedelta(hours=1)),
            _personal(3, 1, created=T0 + timedelta(hours=1), gold=99),
        ]
        for m in models:
            mem.save(m)
            sql.save(m)

        a1, c1 = mem.find_for_player(p1, limit=2)
        b1, d1 = sql.find_for_player(p1, limit=2)
        assert len(a1) == len(b1) == 2
        for x, y in zip(a1, b1):
            _assert_personal_equal(x, y)
        assert (c1 is None) == (d1 is None)
        if c1 is not None and d1 is not None:
            assert c1.created_at == d1.created_at
            assert c1.listing_id == d1.listing_id

        a2, c2 = mem.find_for_player(p1, limit=2, cursor=c1)
        b2, d2 = sql.find_for_player(p1, limit=2, cursor=d1)
        assert len(a2) == len(b2)
        for x, y in zip(a2, b2):
            _assert_personal_equal(x, y)

        assert mem.count_for_player(p1) == sql.count_for_player(p1) == 3

        conn.close()

    def test_factory_from_env_uses_game_db_path(self, tmp_path, monkeypatch) -> None:
        db = tmp_path / "game.sqlite"
        monkeypatch.setenv("GAME_DB_PATH", str(db))
        fac_mem = create_personal_trade_listing_read_model_repository_from_path(None)
        fac_sql = create_personal_trade_listing_read_model_repository_from_path(str(db))
        from_env = create_personal_trade_listing_read_model_repository_from_env()
        assert type(fac_mem).__name__ == "InMemoryPersonalTradeListingReadModelRepository"
        assert type(fac_sql).__name__ == "SqlitePersonalTradeListingReadModelRepository"
        assert type(from_env).__name__ == "SqlitePersonalTradeListingReadModelRepository"


class TestGameDbPathFactories:
    def test_trade_detail_factory_from_env(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("GAME_DB_PATH", str(tmp_path / "td.db"))
        r = create_trade_detail_read_model_repository_from_env()
        assert isinstance(r, SqliteTradeDetailReadModelRepository)

    def test_global_market_factory_from_env(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("GAME_DB_PATH", str(tmp_path / "gm.db"))
        r = create_global_market_listing_read_model_repository_from_env()
        assert isinstance(r, SqliteGlobalMarketListingReadModelRepository)


class TestTradeDetailParity:
    def test_find_detail_parity(self, tmp_path) -> None:
        mem = InMemoryTradeDetailReadModelRepository()
        mem.clear()
        conn = sqlite3.connect(str(tmp_path / "d.db"))
        conn.row_factory = sqlite3.Row
        sql = SqliteTradeDetailReadModelRepository.for_standalone_connection(conn)

        d1 = _detail(1, status=TradeStatus.COMPLETED)
        mem.save(d1)
        sql.save(d1)

        a = mem.find_detail(TradeId(1))
        b = sql.find_detail(TradeId(1))
        assert a is not None and b is not None
        _assert_detail_equal(a, b)
        conn.close()


class TestGlobalMarketParity:
    def test_find_listings_filter_and_count_parity(self, tmp_path) -> None:
        mem = InMemoryGlobalMarketListingReadModelRepository()
        mem.clear()
        conn = sqlite3.connect(str(tmp_path / "m.db"))
        conn.row_factory = sqlite3.Row
        sql = SqliteGlobalMarketListingReadModelRepository.for_standalone_connection(conn)

        rows = [
            _global(1, created=T0 + timedelta(hours=1), name="alpha sword", gold=100),
            _global(2, created=T0 + timedelta(hours=2), name="beta", gold=500),
            _global(3, created=T0, name="gamma sword", gold=50, status=TradeStatus.CANCELLED),
        ]
        for r in rows:
            mem.save(r)
            sql.save(r)

        flt = TradeSearchFilter.active_only()
        assert mem.count_listings(flt) == sql.count_listings(flt) == 2

        flt2 = TradeSearchFilter.by_item_name("sword")
        a, ca = mem.find_listings(flt2, limit=10)
        b, cb = sql.find_listings(flt2, limit=10)
        assert len(a) == len(b)
        for x, y in zip(a, b):
            _assert_global_equal(x, y)
        assert (ca is None) == (cb is None)

        a1, c1 = mem.find_listings(TradeSearchFilter(), limit=1)
        b1, d1 = sql.find_listings(TradeSearchFilter(), limit=1)
        assert len(a1) == len(b1) == 1
        _assert_global_equal(a1[0], b1[0])
        assert c1 is not None and d1 is not None
        a2, _ = mem.find_listings(TradeSearchFilter(), limit=10, cursor=c1)
        b2, _ = sql.find_listings(TradeSearchFilter(), limit=10, cursor=d1)
        assert len(a2) == len(b2)
        for x, y in zip(a2, b2):
            _assert_global_equal(x, y)

        conn.close()
