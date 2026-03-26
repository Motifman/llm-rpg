"""
SqliteUnitOfWork — 接続共有・rollback・Trade ReadModel の autocommit 抑止
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pytest

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.infrastructure.repository.sqlite_trade_read_model_repository import (
    SqliteTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWork,
    SqliteUnitOfWorkFactory,
)


def _count_rows(conn: sqlite3.Connection, table: str) -> int:
    cur = conn.execute(f"SELECT COUNT(*) AS c FROM {table}")
    row = cur.fetchone()
    assert row is not None
    return int(row[0])


def _make_trade(trade_id: int, seller_id: int) -> TradeReadModel:
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
        status=TradeStatus.ACTIVE,
        created_at=datetime(2025, 1, 1, 12, 0, 0),
    )


@pytest.fixture
def shared_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE uow_t1 (id INTEGER PRIMARY KEY, v TEXT NOT NULL);
        CREATE TABLE uow_t2 (id INTEGER PRIMARY KEY, v TEXT NOT NULL);
        """
    )
    conn.commit()
    return conn


class TestSqliteUnitOfWorkConnectionSharing:
    def test_two_writers_use_same_connection_object(self, shared_conn: sqlite3.Connection) -> None:
        uow = SqliteUnitOfWork(connection=shared_conn)
        with uow:
            c1 = uow.connection
            c2 = uow.connection
            assert c1 is c2 is shared_conn
            c1.execute("INSERT INTO uow_t1 (id, v) VALUES (1, 'a')")
            c2.execute("INSERT INTO uow_t2 (id, v) VALUES (1, 'b')")

        shared_conn.row_factory = sqlite3.Row
        assert _count_rows(shared_conn, "uow_t1") == 1
        assert _count_rows(shared_conn, "uow_t2") == 1

    def test_rollback_reverts_all_writes_on_shared_connection(
        self, shared_conn: sqlite3.Connection
    ) -> None:
        uow = SqliteUnitOfWork(connection=shared_conn)
        try:
            with uow:
                uow.connection.execute("INSERT INTO uow_t1 (id, v) VALUES (1, 'a')")
                uow.connection.execute("INSERT INTO uow_t2 (id, v) VALUES (1, 'b')")
                raise RuntimeError("abort")
        except RuntimeError:
            pass

        assert _count_rows(shared_conn, "uow_t1") == 0
        assert _count_rows(shared_conn, "uow_t2") == 0

    def test_factory_owned_file_commits_and_second_session_sees_data(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "game.db"
        fac = SqliteUnitOfWorkFactory(db)
        uow1 = fac.create()
        with uow1:
            uow1.connection.execute("CREATE TABLE IF NOT EXISTS x (id INTEGER PRIMARY KEY)")
            uow1.connection.execute("INSERT INTO x (id) VALUES (7)")

        conn2 = sqlite3.connect(str(db))
        try:
            n = _count_rows(conn2, "x")
            assert n == 1
        finally:
            conn2.close()


class TestSqliteUnitOfWorkTradeReadModel:
    def test_autocommit_false_defers_until_uow_commit(self, tmp_path: Path) -> None:
        db = tmp_path / "t.db"
        fac = SqliteUnitOfWorkFactory(db)
        uow = fac.create()
        uow.begin()
        repo = SqliteTradeReadModelRepository(uow.connection, autocommit=False)
        repo.save(_make_trade(1, 1))
        uow.commit()

        conn2 = sqlite3.connect(str(db))
        try:
            conn2.row_factory = sqlite3.Row
            cur = conn2.execute("SELECT trade_id FROM trade_read_models WHERE trade_id = 1")
            assert cur.fetchone() is not None
        finally:
            conn2.close()

    def test_autocommit_false_rollbacks_trade_row(self, tmp_path: Path) -> None:
        db = tmp_path / "t2.db"
        fac = SqliteUnitOfWorkFactory(db)
        # スキーマだけ先にコミットしておく（失敗トランザクションの rollback で DDL まで巻き戻ると後続 SELECT でテーブルが無い）
        with fac.create() as bootstrap:
            SqliteTradeReadModelRepository(bootstrap.connection, autocommit=False)

        uow = fac.create()
        try:
            with uow:
                repo = SqliteTradeReadModelRepository(uow.connection, autocommit=False)
                repo.save(_make_trade(99, 1))
                raise ValueError("fail")
        except ValueError:
            pass

        conn2 = sqlite3.connect(str(db))
        try:
            conn2.row_factory = sqlite3.Row
            cur = conn2.execute("SELECT trade_id FROM trade_read_models WHERE trade_id = 99")
            assert cur.fetchone() is None
        finally:
            conn2.close()


class TestSqliteUnitOfWorkGuards:
    def test_begin_while_active_raises(self, shared_conn: sqlite3.Connection) -> None:
        uow = SqliteUnitOfWork(connection=shared_conn)
        uow.begin()
        with pytest.raises(RuntimeError, match="already in progress"):
            uow.begin()
        uow.rollback()

    def test_connection_outside_transaction_raises(self, tmp_path: Path) -> None:
        uow = SqliteUnitOfWork(tmp_path / "z.db")
        with pytest.raises(RuntimeError, match="アクティブな SQLite"):
            _ = uow.connection

    def test_commit_without_begin_raises(self, tmp_path: Path) -> None:
        uow = SqliteUnitOfWork(tmp_path / "no_tx.db")
        with pytest.raises(RuntimeError, match="No transaction in progress"):
            uow.commit()

    def test_rollback_without_begin_raises(self, tmp_path: Path) -> None:
        uow = SqliteUnitOfWork(tmp_path / "no_tx2.db")
        with pytest.raises(RuntimeError, match="No transaction in progress"):
            uow.rollback()

    def test_after_owned_commit_connection_property_raises_until_next_begin(
        self, tmp_path: Path
    ) -> None:
        db = tmp_path / "lifecycle.db"
        uow = SqliteUnitOfWork(database=str(db))
        with uow:
            uow.connection.execute("CREATE TABLE IF NOT EXISTS z (id INTEGER PRIMARY KEY)")
        with pytest.raises(RuntimeError, match="アクティブな SQLite"):
            _ = uow.connection
        with uow:
            assert uow.connection is not None

    def test_add_events_outside_transaction_raises(self, tmp_path: Path) -> None:
        uow = SqliteUnitOfWork(tmp_path / "ev.db")
        with pytest.raises(RuntimeError, match="No transaction in progress"):
            uow.add_events([])
