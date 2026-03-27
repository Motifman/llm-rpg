"""SQLite implementation of ItemTradeStatisticsReadModelRepository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import List, Optional

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.item_trade_statistics_read_model import (
    ItemTradeStatisticsReadModel,
)
from ai_rpg_world.domain.trade.repository.item_trade_statistics_read_model_repository import (
    ItemTradeStatisticsReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.item_trade_statistics_read_model_sqlite import (
    init_item_trade_statistics_read_model_schema,
)


def _dt_to_str(value: datetime) -> str:
    return value.isoformat()


def _str_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_model(row: sqlite3.Row) -> ItemTradeStatisticsReadModel:
    return ItemTradeStatisticsReadModel(
        item_spec_id=ItemSpecId(int(row["item_spec_id"])),
        min_price=None if row["min_price"] is None else int(row["min_price"]),
        max_price=None if row["max_price"] is None else int(row["max_price"]),
        avg_price=None if row["avg_price"] is None else float(row["avg_price"]),
        median_price=None if row["median_price"] is None else int(row["median_price"]),
        total_trades=int(row["total_trades"]),
        success_rate=float(row["success_rate"]),
        last_updated=_str_to_dt(str(row["last_updated"])),
    )


class SqliteItemTradeStatisticsReadModelRepository(
    ItemTradeStatisticsReadModelRepository
):
    def __init__(
        self, connection: sqlite3.Connection, *, _commits_after_write: bool
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_item_trade_statistics_read_model_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteItemTradeStatisticsReadModelRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteItemTradeStatisticsReadModelRepository":
        return cls(connection, _commits_after_write=False)

    def find_by_id(
        self, entity_id: ItemSpecId
    ) -> Optional[ItemTradeStatisticsReadModel]:
        row = self._conn.execute(
            "SELECT * FROM item_trade_statistics_read_models WHERE item_spec_id = ?",
            (int(entity_id),),
        ).fetchone()
        return None if row is None else _row_to_model(row)

    def find_by_ids(
        self, entity_ids: List[ItemSpecId]
    ) -> List[ItemTradeStatisticsReadModel]:
        return [
            model
            for entity_id in entity_ids
            if (model := self.find_by_id(entity_id)) is not None
        ]

    def save(
        self, entity: ItemTradeStatisticsReadModel
    ) -> ItemTradeStatisticsReadModel:
        self._conn.execute(
            """
            INSERT INTO item_trade_statistics_read_models (
                item_spec_id, min_price, max_price, avg_price, median_price,
                total_trades, success_rate, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_spec_id) DO UPDATE SET
                min_price = excluded.min_price,
                max_price = excluded.max_price,
                avg_price = excluded.avg_price,
                median_price = excluded.median_price,
                total_trades = excluded.total_trades,
                success_rate = excluded.success_rate,
                last_updated = excluded.last_updated
            """,
            (
                int(entity.item_spec_id),
                entity.min_price,
                entity.max_price,
                entity.avg_price,
                entity.median_price,
                int(entity.total_trades),
                float(entity.success_rate),
                _dt_to_str(entity.last_updated),
            ),
        )
        if self._commits_after_write:
            self._conn.commit()
        return entity

    def delete(self, entity_id: ItemSpecId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM item_trade_statistics_read_models WHERE item_spec_id = ?",
            (int(entity_id),),
        )
        if self._commits_after_write:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[ItemTradeStatisticsReadModel]:
        rows = self._conn.execute(
            """
            SELECT * FROM item_trade_statistics_read_models
            ORDER BY item_spec_id ASC
            """
        ).fetchall()
        return [_row_to_model(row) for row in rows]

    def find_statistics(
        self, item_spec_id: ItemSpecId
    ) -> Optional[ItemTradeStatisticsReadModel]:
        return self.find_by_id(item_spec_id)
