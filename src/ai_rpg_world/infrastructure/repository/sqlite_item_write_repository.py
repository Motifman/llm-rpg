"""アイテム集約の SQLite 実装（ゲーム書き込み DB）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.durability import Durability
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_repository import (
    SqliteItemSpecRepository,
    SqliteItemSpecWriter,
)


class SqliteItemWriteRepository(ItemRepository):
    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        _commits_after_write: bool,
        event_sink: Any = None,
    ) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        self._event_sink = event_sink
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqliteItemWriteRepository:
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqliteItemWriteRepository:
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()
        return

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def _row_to_aggregate(self, row: sqlite3.Row) -> ItemAggregate:
        spec_repo = SqliteItemSpecRepository.for_connection(self._conn)
        spec = spec_repo.find_by_id(ItemSpecId(int(row["item_spec_id"])))
        if spec is None:
            raise RuntimeError("game_items が参照する item_spec_id に対応する game_item_specs が見つかりません")
        durability = None
        if row["durability_current"] is not None and spec.durability_max is not None:
            durability = Durability(current=int(row["durability_current"]), max_value=int(spec.durability_max))
        return ItemAggregate.create_from_instance(
            ItemInstance(
                item_instance_id=ItemInstanceId(int(row["item_instance_id"])),
                item_spec=spec,
                durability=durability,
                quantity=int(row["quantity"]),
            )
        )

    def _all_aggregates(self) -> List[ItemAggregate]:
        cur = self._conn.execute("SELECT * FROM game_items")
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def generate_item_instance_id(self) -> ItemInstanceId:
        self._assert_shared_transaction_active()
        iid = ItemInstanceId(allocate_sequence_value(self._conn, "item_instance_id"))
        self._finalize_write()
        return iid

    def find_by_id(self, item_instance_id: ItemInstanceId) -> Optional[ItemAggregate]:
        cur = self._conn.execute("SELECT * FROM game_items WHERE item_instance_id = ?", (int(item_instance_id),))
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._row_to_aggregate(row))

    def find_by_ids(self, item_instance_ids: List[ItemInstanceId]) -> List[ItemAggregate]:
        return [x for iid in item_instance_ids for x in [self.find_by_id(iid)] if x is not None]

    def find_all(self) -> List[ItemAggregate]:
        return self._all_aggregates()

    def save(self, aggregate: ItemAggregate) -> ItemAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(aggregate)
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        try:
            SqliteItemSpecWriter.for_shared_unit_of_work(self._conn).replace_spec(aggregate.item_spec)
            self._conn.execute(
                """
                INSERT INTO game_items (item_instance_id, item_spec_id, quantity, durability_current)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(item_instance_id) DO UPDATE SET
                    item_spec_id = excluded.item_spec_id,
                    quantity = excluded.quantity,
                    durability_current = excluded.durability_current
                """,
                (
                    int(aggregate.item_instance_id),
                    int(aggregate.item_spec.item_spec_id),
                    int(aggregate.quantity),
                    None if aggregate.durability is None else int(aggregate.durability.current),
                ),
            )
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return copy.deepcopy(aggregate)

    def delete(self, item_instance_id: ItemInstanceId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute("DELETE FROM game_items WHERE item_instance_id = ?", (int(item_instance_id),))
        self._finalize_write()
        return cur.rowcount > 0

    def find_by_spec_id(self, item_spec_id: ItemSpecId) -> List[ItemAggregate]:
        cur = self._conn.execute("SELECT * FROM game_items WHERE item_spec_id = ? ORDER BY item_instance_id ASC", (int(item_spec_id),))
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def find_by_type(self, item_type: ItemType) -> List[ItemAggregate]:
        cur = self._conn.execute(
            """
            SELECT item.*
            FROM game_items item
            JOIN game_item_specs spec ON spec.item_spec_id = item.item_spec_id
            WHERE spec.item_type = ?
            ORDER BY item.item_instance_id ASC
            """,
            (item_type.value,),
        )
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def find_by_rarity(self, rarity: Rarity) -> List[ItemAggregate]:
        cur = self._conn.execute(
            """
            SELECT item.*
            FROM game_items item
            JOIN game_item_specs spec ON spec.item_spec_id = item.item_spec_id
            WHERE spec.rarity = ?
            ORDER BY item.item_instance_id ASC
            """,
            (rarity.value,),
        )
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def find_broken_items(self) -> List[ItemAggregate]:
        cur = self._conn.execute("SELECT * FROM game_items WHERE durability_current = 0 ORDER BY item_instance_id ASC")
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def find_tradeable_items(self) -> List[ItemAggregate]:
        cur = self._conn.execute(
            """
            SELECT item.*
            FROM game_items item
            JOIN game_item_specs spec ON spec.item_spec_id = item.item_spec_id
            WHERE spec.is_tradeable = 1
            ORDER BY item.item_instance_id ASC
            """
        )
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def find_by_owner_id(self, owner_id: int) -> List[ItemAggregate]:
        owner_id_value = int(owner_id)
        row = self._conn.execute(
            "SELECT 1 FROM game_player_inventories WHERE player_id = ?",
            (owner_id_value,),
        ).fetchone()
        if row is None:
            return []
        cur = self._conn.execute(
            """
            SELECT DISTINCT item.item_instance_id, item.item_spec_id, item.quantity, item.durability_current
            FROM game_items item
            JOIN (
                SELECT item_instance_id
                FROM game_player_inventory_slots
                WHERE player_id = ? AND item_instance_id IS NOT NULL
                UNION
                SELECT item_instance_id
                FROM game_player_equipment_slots
                WHERE player_id = ? AND item_instance_id IS NOT NULL
                UNION
                SELECT item_instance_id
                FROM game_player_reserved_items
                WHERE player_id = ?
            ) owned ON owned.item_instance_id = item.item_instance_id
            ORDER BY item.item_instance_id ASC
            """,
            (owner_id_value, owner_id_value, owner_id_value),
        )
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]


__all__ = ["SqliteItemWriteRepository"]
