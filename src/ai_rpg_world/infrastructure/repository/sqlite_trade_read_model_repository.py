"""
SqliteTradeReadModelRepository — TradeReadModel の SQLite 実装
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.trade_read_model import TradeReadModel
from ai_rpg_world.domain.trade.repository.trade_read_model_repository import (
    TradeCursor,
    TradeReadModelRepository,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.infrastructure.repository.trade_read_model_sqlite import (
    init_trade_read_model_schema,
)


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _row_to_model(row: sqlite3.Row) -> TradeReadModel:
    return TradeReadModel(
        trade_id=int(row["trade_id"]),
        seller_id=int(row["seller_id"]),
        seller_name=str(row["seller_name"]),
        buyer_id=row["buyer_id"],
        buyer_name=row["buyer_name"],
        requested_gold=int(row["requested_gold"]),
        status=str(row["status"]),
        created_at=_str_to_dt(str(row["created_at"])),
        item_instance_id=int(row["item_instance_id"]),
        item_name=str(row["item_name"]),
        item_quantity=int(row["item_quantity"]),
        item_type=str(row["item_type"]),
        item_rarity=str(row["item_rarity"]),
        item_description=str(row["item_description"]),
        item_equipment_type=row["item_equipment_type"],
        durability_current=row["durability_current"],
        durability_max=row["durability_max"],
    )


def _model_tuple(m: TradeReadModel) -> Tuple[Any, ...]:
    return (
        m.trade_id,
        m.seller_id,
        m.seller_name,
        m.buyer_id,
        m.buyer_name,
        m.requested_gold,
        m.status,
        _dt_to_str(m.created_at),
        m.item_instance_id,
        m.item_name,
        m.item_quantity,
        m.item_type,
        m.item_rarity,
        m.item_description,
        m.item_equipment_type,
        m.durability_current,
        m.durability_max,
    )


def _cursor_sql_params(cursor: Optional[TradeCursor]) -> Tuple[str, List[Any]]:
    if cursor is None:
        return "", []
    c_at = _dt_to_str(cursor.created_at)
    return (
        " AND (created_at < ? OR (created_at = ? AND trade_id > ?))",
        [c_at, c_at, cursor.trade_id],
    )


class SqliteTradeReadModelRepository(TradeReadModelRepository):
    """TradeReadModel を SQLite に保持するリポジトリ"""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_trade_read_model_schema(connection)

    def find_by_id(self, entity_id: TradeId) -> Optional[TradeReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM trade_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        return _row_to_model(row) if row else None

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[TradeReadModel]:
        if not entity_ids:
            return []
        placeholders = ",".join("?" for _ in entity_ids)
        ids = [int(i) for i in entity_ids]
        cur = self._conn.execute(
            f"SELECT * FROM trade_read_models WHERE trade_id IN ({placeholders})",
            ids,
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def save(self, entity: TradeReadModel) -> TradeReadModel:
        self._conn.execute(
            """
            INSERT INTO trade_read_models (
                trade_id, seller_id, seller_name, buyer_id, buyer_name,
                requested_gold, status, created_at,
                item_instance_id, item_name, item_quantity, item_type, item_rarity,
                item_description, item_equipment_type, durability_current, durability_max
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                seller_id = excluded.seller_id,
                seller_name = excluded.seller_name,
                buyer_id = excluded.buyer_id,
                buyer_name = excluded.buyer_name,
                requested_gold = excluded.requested_gold,
                status = excluded.status,
                created_at = excluded.created_at,
                item_instance_id = excluded.item_instance_id,
                item_name = excluded.item_name,
                item_quantity = excluded.item_quantity,
                item_type = excluded.item_type,
                item_rarity = excluded.item_rarity,
                item_description = excluded.item_description,
                item_equipment_type = excluded.item_equipment_type,
                durability_current = excluded.durability_current,
                durability_max = excluded.durability_max
            """,
            _model_tuple(entity),
        )
        self._conn.commit()
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM trade_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[TradeReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM trade_read_models ORDER BY created_at DESC, trade_id ASC"
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def _select_paged(
        self,
        base_where: str,
        params: Sequence[Any],
        limit: int,
        cursor: Optional[TradeCursor],
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        cs_sql, cs_params = _cursor_sql_params(cursor)
        sql = (
            "SELECT * FROM trade_read_models WHERE "
            + base_where
            + cs_sql
            + " ORDER BY created_at DESC, trade_id ASC LIMIT ?"
        )
        q = list(params) + cs_params + [limit + 1]
        cur = self._conn.execute(sql, q)
        rows = cur.fetchall()
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        models = [_row_to_model(r) for r in page_rows]
        next_cursor: Optional[TradeCursor] = None
        if has_more and models:
            last = models[-1]
            next_cursor = TradeCursor(created_at=last.created_at, trade_id=last.trade_id)
        return models, next_cursor

    def find_recent_trades(
        self, limit: int = 10, cursor: Optional[TradeCursor] = None
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        return self._select_paged("1 = 1", [], limit, cursor)

    def find_trades_for_player(
        self,
        player_id: PlayerId,
        limit: int = 10,
        cursor: Optional[TradeCursor] = None,
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        pid = int(player_id)
        return self._select_paged(
            "(seller_id = ? OR buyer_id = ?)",
            [pid, pid],
            limit,
            cursor,
        )

    def find_active_trades_as_seller(
        self,
        seller_id: PlayerId,
        limit: int = 10,
        cursor: Optional[TradeCursor] = None,
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        sid = int(seller_id)
        return self._select_paged(
            "seller_id = ? AND status = ?",
            [sid, TradeStatus.ACTIVE.name],
            limit,
            cursor,
        )

    def find_active_trades(
        self, limit: int = 50, cursor: Optional[TradeCursor] = None
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        return self._select_paged(
            "status = ?",
            [TradeStatus.ACTIVE.name],
            limit,
            cursor,
        )

    def search_trades(
        self,
        filter: TradeSearchFilter,
        limit: int = 20,
        cursor: Optional[TradeCursor] = None,
    ) -> Tuple[List[TradeReadModel], Optional[TradeCursor]]:
        conds: List[str] = []
        params: List[Any] = []

        if filter.item_name:
            conds.append("LOWER(item_name) LIKE ?")
            params.append(f"%{filter.item_name.lower()}%")

        if filter.item_types:
            placeholders = ",".join("?" for _ in filter.item_types)
            conds.append(f"item_type IN ({placeholders})")
            params.extend(t.value for t in filter.item_types)

        if filter.rarities:
            placeholders = ",".join("?" for _ in filter.rarities)
            conds.append(f"item_rarity IN ({placeholders})")
            params.extend(r.value for r in filter.rarities)

        if filter.equipment_types:
            placeholders = ",".join("?" for _ in filter.equipment_types)
            conds.append(f"item_equipment_type IN ({placeholders})")
            params.extend(et.value for et in filter.equipment_types)

        if filter.min_price is not None:
            conds.append("requested_gold >= ?")
            params.append(filter.min_price)

        if filter.max_price is not None:
            conds.append("requested_gold <= ?")
            params.append(filter.max_price)

        if filter.statuses:
            placeholders = ",".join("?" for _ in filter.statuses)
            conds.append(f"status IN ({placeholders})")
            params.extend(s.name for s in filter.statuses)

        base_where = " AND ".join(conds) if conds else "1 = 1"
        return self._select_paged(base_where, params, limit, cursor)
