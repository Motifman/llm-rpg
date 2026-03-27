"""SqlitePersonalTradeListingReadModelRepository"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, List, Optional, Sequence, Tuple

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.read_model.personal_trade_listing_read_model import (
    PersonalTradeListingReadModel,
)
from ai_rpg_world.domain.trade.repository.cursor import ListingCursor
from ai_rpg_world.domain.trade.repository.personal_trade_listing_read_model_repository import (
    PersonalTradeListingReadModelRepository,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.infrastructure.repository.personal_trade_listing_read_model_sqlite import (
    init_personal_trade_listing_read_model_schema,
)


def _dt_to_str(dt: datetime) -> str:
    return dt.isoformat()


def _str_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _row_to_model(row: sqlite3.Row) -> PersonalTradeListingReadModel:
    eq = row["item_equipment_type"]
    return PersonalTradeListingReadModel(
        trade_id=TradeId(int(row["trade_id"])),
        item_spec_id=ItemSpecId(int(row["item_spec_id"])),
        item_instance_id=ItemInstanceId(int(row["item_instance_id"])),
        recipient_player_id=PlayerId(int(row["recipient_player_id"])),
        item_name=str(row["item_name"]),
        item_quantity=int(row["item_quantity"]),
        item_type=ItemType(str(row["item_type"])),
        item_rarity=Rarity(str(row["item_rarity"])),
        item_equipment_type=EquipmentType(str(eq)) if eq is not None else None,
        durability_current=row["durability_current"],
        durability_max=row["durability_max"],
        requested_gold=int(row["requested_gold"]),
        seller_name=str(row["seller_name"]),
        created_at=_str_to_dt(str(row["created_at"])),
    )


def _model_tuple(m: PersonalTradeListingReadModel) -> Tuple[Any, ...]:
    return (
        int(m.trade_id),
        int(m.item_spec_id),
        int(m.item_instance_id),
        int(m.recipient_player_id),
        str(m.item_name),
        int(m.item_quantity),
        m.item_type.value,
        m.item_rarity.value,
        m.item_equipment_type.value if m.item_equipment_type is not None else None,
        m.durability_current,
        m.durability_max,
        int(m.requested_gold),
        str(m.seller_name),
        _dt_to_str(m.created_at),
    )


def _listing_cursor_sql(cursor: Optional[ListingCursor]) -> Tuple[str, List[Any]]:
    """InMemoryPersonalTradeListingReadModelRepository と同順（created_at DESC, trade_id DESC）の次ページ。"""
    if cursor is None:
        return "", []
    c_at = _dt_to_str(cursor.created_at)
    return (
        " AND (created_at < ? OR (created_at = ? AND trade_id < ?))",
        [c_at, c_at, cursor.listing_id],
    )


class SqlitePersonalTradeListingReadModelRepository(PersonalTradeListingReadModelRepository):
    def __init__(
        self, connection: sqlite3.Connection, *, autocommit: bool = True
    ) -> None:
        self._conn = connection
        self._autocommit = autocommit
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_personal_trade_listing_read_model_schema(connection)

    def find_by_id(self, entity_id: TradeId) -> Optional[PersonalTradeListingReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM personal_trade_listing_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        return _row_to_model(row) if row else None

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[PersonalTradeListingReadModel]:
        if not entity_ids:
            return []
        ph = ",".join("?" for _ in entity_ids)
        ids = [int(i) for i in entity_ids]
        cur = self._conn.execute(
            f"SELECT * FROM personal_trade_listing_read_models WHERE trade_id IN ({ph})",
            ids,
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def save(self, entity: PersonalTradeListingReadModel) -> PersonalTradeListingReadModel:
        self._conn.execute(
            """
            INSERT INTO personal_trade_listing_read_models (
                trade_id, item_spec_id, item_instance_id, recipient_player_id,
                item_name, item_quantity, item_type, item_rarity, item_equipment_type,
                durability_current, durability_max, requested_gold, seller_name, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                item_spec_id = excluded.item_spec_id,
                item_instance_id = excluded.item_instance_id,
                recipient_player_id = excluded.recipient_player_id,
                item_name = excluded.item_name,
                item_quantity = excluded.item_quantity,
                item_type = excluded.item_type,
                item_rarity = excluded.item_rarity,
                item_equipment_type = excluded.item_equipment_type,
                durability_current = excluded.durability_current,
                durability_max = excluded.durability_max,
                requested_gold = excluded.requested_gold,
                seller_name = excluded.seller_name,
                created_at = excluded.created_at
            """,
            _model_tuple(entity),
        )
        if self._autocommit:
            self._conn.commit()
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM personal_trade_listing_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        if self._autocommit:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[PersonalTradeListingReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM personal_trade_listing_read_models ORDER BY trade_id ASC"
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def find_for_player(
        self,
        player_id: PlayerId,
        limit: int = 20,
        cursor: Optional[ListingCursor] = None,
    ) -> Tuple[List[PersonalTradeListingReadModel], Optional[ListingCursor]]:
        cs_sql, cs_params = _listing_cursor_sql(cursor)
        sql = (
            "SELECT * FROM personal_trade_listing_read_models WHERE recipient_player_id = ?"
            + cs_sql
            + " ORDER BY created_at DESC, trade_id DESC LIMIT ?"
        )
        q: Sequence[Any] = [int(player_id)] + cs_params + [limit + 1]
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

    def count_for_player(self, player_id: PlayerId) -> int:
        cur = self._conn.execute(
            "SELECT COUNT(*) AS c FROM personal_trade_listing_read_models WHERE recipient_player_id = ?",
            (int(player_id),),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row["c"])
