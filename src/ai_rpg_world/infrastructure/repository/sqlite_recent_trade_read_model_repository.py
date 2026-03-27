"""SQLite implementation of RecentTradeReadModelRepository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.recent_trade_read_model import (
    RecentTradeData,
    RecentTradeReadModel,
)
from ai_rpg_world.domain.trade.repository.recent_trade_read_model_repository import (
    RecentTradeReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.recent_trade_read_model_sqlite import (
    init_recent_trade_read_model_schema,
)


def _dt_to_str(value: datetime) -> str:
    return value.isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqliteRecentTradeReadModelRepository(RecentTradeReadModelRepository):
    def __init__(
        self, connection: sqlite3.Connection, *, _commits_after_write: bool
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_recent_trade_read_model_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteRecentTradeReadModelRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteRecentTradeReadModelRepository":
        return cls(connection, _commits_after_write=False)

    def _entry_rows(self, item_spec_id: ItemSpecId) -> list[sqlite3.Row]:
        cur = self._conn.execute(
            """
            SELECT trade_id, price, traded_at
            FROM recent_trade_read_model_entries
            WHERE item_spec_id = ?
            ORDER BY trade_index ASC
            """,
            (int(item_spec_id),),
        )
        return list(cur.fetchall())

    def _build_model(self, row: sqlite3.Row) -> RecentTradeReadModel:
        entries = [
            RecentTradeData(
                trade_id=int(entry_row["trade_id"]),
                price=int(entry_row["price"]),
                traded_at=_str_to_dt(str(entry_row["traded_at"])),
            )
            for entry_row in self._entry_rows(ItemSpecId(int(row["item_spec_id"])))
        ]
        return RecentTradeReadModel(
            item_spec_id=ItemSpecId(int(row["item_spec_id"])),
            item_name=str(row["item_name"]),
            recent_trades=entries,
            last_updated=_str_to_dt(str(row["last_updated"])),
        )

    def find_by_id(self, entity_id: ItemSpecId) -> Optional[RecentTradeReadModel]:
        row = self._conn.execute(
            """
            SELECT item_spec_id, item_name, last_updated
            FROM recent_trade_read_models
            WHERE item_spec_id = ?
            """,
            (int(entity_id),),
        ).fetchone()
        return None if row is None else self._build_model(row)

    def find_by_ids(self, entity_ids: List[ItemSpecId]) -> List[RecentTradeReadModel]:
        return [
            model
            for entity_id in entity_ids
            if (model := self.find_by_id(entity_id)) is not None
        ]

    def save(self, entity: RecentTradeReadModel) -> RecentTradeReadModel:
        self._conn.execute(
            """
            INSERT INTO recent_trade_read_models (item_spec_id, item_name, last_updated)
            VALUES (?, ?, ?)
            ON CONFLICT(item_spec_id) DO UPDATE SET
                item_name = excluded.item_name,
                last_updated = excluded.last_updated
            """,
            (
                int(entity.item_spec_id),
                entity.item_name,
                _dt_to_str(entity.last_updated),
            ),
        )
        self._conn.execute(
            "DELETE FROM recent_trade_read_model_entries WHERE item_spec_id = ?",
            (int(entity.item_spec_id),),
        )
        self._conn.executemany(
            """
            INSERT INTO recent_trade_read_model_entries (
                item_spec_id, trade_index, trade_id, price, traded_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    int(entity.item_spec_id),
                    index,
                    int(trade.trade_id),
                    int(trade.price),
                    _dt_to_str(trade.traded_at),
                )
                for index, trade in enumerate(entity.recent_trades)
            ],
        )
        if self._commits_after_write:
            self._conn.commit()
        return entity

    def delete(self, entity_id: ItemSpecId) -> bool:
        self._conn.execute(
            "DELETE FROM recent_trade_read_model_entries WHERE item_spec_id = ?",
            (int(entity_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM recent_trade_read_models WHERE item_spec_id = ?",
            (int(entity_id),),
        )
        if self._commits_after_write:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[RecentTradeReadModel]:
        rows = self._conn.execute(
            """
            SELECT item_spec_id, item_name, last_updated
            FROM recent_trade_read_models
            ORDER BY item_spec_id ASC
            """
        ).fetchall()
        return [self._build_model(row) for row in rows]

    def find_by_item_name(self, item_name: str) -> Optional[RecentTradeReadModel]:
        row = self._conn.execute(
            """
            SELECT item_spec_id, item_name, last_updated
            FROM recent_trade_read_models
            WHERE item_name = ?
            """,
            (item_name,),
        ).fetchone()
        return None if row is None else self._build_model(row)
