"""SqliteTradeDetailReadModelRepository"""

from __future__ import annotations

import sqlite3
from typing import Any, List, Optional, Tuple

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.trade.read_model.trade_detail_read_model import TradeDetailReadModel
from ai_rpg_world.domain.trade.repository.trade_detail_read_model_repository import (
    TradeDetailReadModelRepository,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.infrastructure.repository.trade_detail_read_model_sqlite import (
    init_trade_detail_read_model_schema,
)


def _row_to_model(row: sqlite3.Row) -> TradeDetailReadModel:
    eq = row["item_equipment_type"]
    return TradeDetailReadModel(
        trade_id=TradeId(int(row["trade_id"])),
        item_spec_id=ItemSpecId(int(row["item_spec_id"])),
        item_instance_id=ItemInstanceId(int(row["item_instance_id"])),
        item_name=str(row["item_name"]),
        item_quantity=int(row["item_quantity"]),
        item_type=ItemType(str(row["item_type"])),
        item_rarity=Rarity(str(row["item_rarity"])),
        item_description=str(row["item_description"]),
        item_equipment_type=EquipmentType(str(eq)) if eq is not None else None,
        durability_current=row["durability_current"],
        durability_max=row["durability_max"],
        requested_gold=int(row["requested_gold"]),
        seller_name=str(row["seller_name"]),
        buyer_name=row["buyer_name"],
        status=str(row["status"]),
    )


def _model_tuple(m: TradeDetailReadModel) -> Tuple[Any, ...]:
    return (
        int(m.trade_id),
        int(m.item_spec_id),
        int(m.item_instance_id),
        str(m.item_name),
        int(m.item_quantity),
        m.item_type.value,
        m.item_rarity.value,
        str(m.item_description),
        m.item_equipment_type.value if m.item_equipment_type is not None else None,
        m.durability_current,
        m.durability_max,
        int(m.requested_gold),
        str(m.seller_name),
        m.buyer_name,
        str(m.status),
    )


class SqliteTradeDetailReadModelRepository(TradeDetailReadModelRepository):
    def __init__(
        self, connection: sqlite3.Connection, *, _commits_after_write: bool
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_trade_detail_read_model_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> SqliteTradeDetailReadModelRepository:
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> SqliteTradeDetailReadModelRepository:
        return cls(connection, _commits_after_write=False)

    def find_by_id(self, entity_id: TradeId) -> Optional[TradeDetailReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM trade_detail_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        return _row_to_model(row) if row else None

    def find_by_ids(self, entity_ids: List[TradeId]) -> List[TradeDetailReadModel]:
        if not entity_ids:
            return []
        ph = ",".join("?" for _ in entity_ids)
        ids = [int(i) for i in entity_ids]
        cur = self._conn.execute(
            f"SELECT * FROM trade_detail_read_models WHERE trade_id IN ({ph})",
            ids,
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def save(self, entity: TradeDetailReadModel) -> TradeDetailReadModel:
        self._conn.execute(
            """
            INSERT INTO trade_detail_read_models (
                trade_id, item_spec_id, item_instance_id, item_name, item_quantity,
                item_type, item_rarity, item_description, item_equipment_type,
                durability_current, durability_max, requested_gold,
                seller_name, buyer_name, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                item_spec_id = excluded.item_spec_id,
                item_instance_id = excluded.item_instance_id,
                item_name = excluded.item_name,
                item_quantity = excluded.item_quantity,
                item_type = excluded.item_type,
                item_rarity = excluded.item_rarity,
                item_description = excluded.item_description,
                item_equipment_type = excluded.item_equipment_type,
                durability_current = excluded.durability_current,
                durability_max = excluded.durability_max,
                requested_gold = excluded.requested_gold,
                seller_name = excluded.seller_name,
                buyer_name = excluded.buyer_name,
                status = excluded.status
            """,
            _model_tuple(entity),
        )
        if self._commits_after_write:
            self._conn.commit()
        return entity

    def delete(self, entity_id: TradeId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM trade_detail_read_models WHERE trade_id = ?",
            (int(entity_id),),
        )
        if self._commits_after_write:
            self._conn.commit()
        return cur.rowcount > 0

    def find_all(self) -> List[TradeDetailReadModel]:
        cur = self._conn.execute(
            "SELECT * FROM trade_detail_read_models ORDER BY trade_id ASC"
        )
        return [_row_to_model(r) for r in cur.fetchall()]

    def find_detail(self, trade_id: TradeId) -> Optional[TradeDetailReadModel]:
        return self.find_by_id(trade_id)
