"""SqliteGlobalMarketListingReadModelRepository"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.read_model.global_market_listing_read_model import (
    GlobalMarketListingReadModel,
)
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor
from ai_rpg_world.domain.trade.repository.global_market_listing_read_model_repository import (
    GlobalMarketListingReadModelRepository,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from ai_rpg_world.infrastructure.repository.global_market_listing_read_model_sqlite import (
    init_global_market_listing_read_model_schema,
)


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _row_to_model(row: sqlite3.Row) -> GlobalMarketListingReadModel:
    eq = row["item_equipment_type"]
    return GlobalMarketListingReadModel(
        trade_id=TradeId(int(row["trade_id"])),
        item_spec_id=ItemSpecId(int(row["item_spec_id"])),
        item_instance_id=ItemInstanceId(int(row["item_instance_id"])),
        item_name=str(row["item_name"]),
        item_quantity=int(row["item_quantity"]),
        item_type=ItemType(str(row["item_type"])),
        item_rarity=Rarity(str(row["item_rarity"])),
        item_equipment_type=EquipmentType(str(eq)) if eq is not None else None,
        status=TradeStatus(str(row["status"])),
        created_at=_str_to_dt(str(row["created_at"])),
        durability_current=row["durability_current"],
        durability_max=row["durability_max"],
        requested_gold=int(row["requested_gold"]),
    )


def _model_tuple(m: GlobalMarketListingReadModel) -> Tuple[Any, ...]:
    return (
        int(m.trade_id),
        int(m.item_spec_id),
        int(m.item_instance_id),
        str(m.item_name),
        int(m.item_quantity),
        m.item_type.value,
        m.item_rarity.value,
        m.item_equipment_type.value if m.item_equipment_type is not None else None,
        m.status.value,
        _dt_to_str(m.created_at),
        m.durability_current,
        m.durability_max,
        int(m.requested_gold),
    )


def _global_filter_sql(f: TradeSearchFilter) -> Tuple[str, List[Any]]:
    """InMemoryGlobalMarketListingReadModelRepository._matches_filter に相当する WHERE 断片。"""
    conds: List[str] = []
    params: List[Any] = []
    if f.item_name:
        conds.append("LOWER(item_name) LIKE ?")
        params.append(f"%{f.item_name.lower()}%")
    if f.item_types:
        ph = ",".join("?" for _ in f.item_types)
        conds.append(f"item_type IN ({ph})")
        params.extend(t.value for t in f.item_types)
    if f.rarities:
        ph = ",".join("?" for _ in f.rarities)
        conds.append(f"item_rarity IN ({ph})")
        params.extend(r.value for r in f.rarities)
    if f.equipment_types:
        ph = ",".join("?" for _ in f.equipment_types)
        conds.append(f"(item_equipment_type IS NOT NULL AND item_equipment_type IN ({ph}))")
        params.extend(et.value for et in f.equipment_types)
    if f.min_price is not None:
        conds.append("requested_gold >= ?")
        params.append(f.min_price)
    if f.max_price is not None:
        conds.append("requested_gold <= ?")
        params.append(f.max_price)
    if f.statuses:
        ph = ",".join("?" for _ in f.statuses)
        conds.append(f"status IN ({ph})")
        params.extend(s.value for s in f.statuses)
    if not conds:
        return "1 = 1", []
    return " AND ".join(conds), params


def _listing_cursor_sql(cursor: Optional[ListingCursor]) -> Tuple[str, List[Any]]:
    if cursor is None:
        return "", []
    c_at = _dt_to_str(cursor.created_at)
    return (
        " AND (created_at < ? OR (created_at = ? AND trade_id < ?))",
        [c_at, c_at, cursor.listing_id],
    )


class SqliteGlobalMarketListingReadModelRepository(GlobalMarketListingReadModelRepository):
    def __init__(
        self, connection: sqlite3.Connection, *, _commits_after_write: bool
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_global_market_listing_read_model_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> SqliteGlobalMarketListingReadModelRepository:
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> SqliteGlobalMarketListingReadModelRepository:
        return cls(connection, _commits_after_write=False)

    def find_by_id(self, entity_id: TradeId) -> Optional[GlobalMarketListingReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM global_market_listing_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        return _row_to_model(row) if row else None

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[GlobalMarketListingReadModel]:
        if not entity_ids:
            return []
        ph = ",".join("?" for _ in entity_ids)
        ids = [int(i) for i in entity_ids]
        cur = self._conn.execute(
            f"SELECT * FROM global_market_listing_read_models WHERE trade_id IN ({ph})",
            ids,
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def save(self, entity: GlobalMarketListingReadModel) -> GlobalMarketListingReadModel:
        self._conn.execute(
            """
            INSERT INTO global_market_listing_read_models (
                trade_id, item_spec_id, item_instance_id, item_name, item_quantity,
                item_type, item_rarity, item_equipment_type, status, created_at,
                durability_current, durability_max, requested_gold
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                item_spec_id = excluded.item_spec_id,
                item_instance_id = excluded.item_instance_id,
                item_name = excluded.item_name,
                item_quantity = excluded.item_quantity,
                item_type = excluded.item_type,
                item_rarity = excluded.item_rarity,
                item_equipment_type = excluded.item_equipment_type,
                status = excluded.status,
                created_at = excluded.created_at,
                durability_current = excluded.durability_current,
                durability_max = excluded.durability_max,
                requested_gold = excluded.requested_gold
            """,
            _model_tuple(entity),
        )
        if self._commits_after_write:
            self._conn.commit()
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM global_market_listing_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        if self._commits_after_write:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[GlobalMarketListingReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM global_market_listing_read_models ORDER BY trade_id ASC"
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def find_listings(
        self,
        filter_condition: TradeSearchFilter,
        limit: int = 50,
        cursor: Optional[ListingCursor] = None,
    ) -> Tuple[List[GlobalMarketListingReadModel], Optional[ListingCursor]]:
        filt_sql, filt_params = _global_filter_sql(filter_condition)
        cs_sql, cs_params = _listing_cursor_sql(cursor)
        sql = (
            "SELECT * FROM global_market_listing_read_models WHERE "
            + filt_sql
            + cs_sql
            + " ORDER BY created_at DESC, trade_id DESC LIMIT ?"
        )
        q: Sequence[Any] = list(filt_params) + cs_params + [limit + 1]
        cur = self._conn.execute(sql, q)
        rows = cur.fetchall()
        has_more = len(rows) > limit
        page = rows[:limit]
        models = [_row_to_model(r) for r in page]
        next_c: Optional[ListingCursor] = None
        if has_more and models:
            last = models[-1]
            next_c = ListingCursor(created_at=last.created_at, listing_id=int(last.trade_id))
        return models, next_c

    def count_listings(self, filter_condition: TradeSearchFilter) -> int:
        filt_sql, filt_params = _global_filter_sql(filter_condition)
        cur = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM global_market_listing_read_models WHERE {filt_sql}",
            filt_params,
        )
        row = cur.fetchone()
        assert row is not None
        return int(row["c"])
