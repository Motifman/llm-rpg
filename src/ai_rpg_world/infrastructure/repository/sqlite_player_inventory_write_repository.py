"""プレイヤーインベントリ集約の SQLite 実装（ゲーム書き込み DB）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import init_game_write_schema
from ai_rpg_world.infrastructure.repository.sqlite_player_state_codec import build_player_inventory


class SqlitePlayerInventoryWriteRepository(PlayerInventoryRepository):
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
    ) -> SqlitePlayerInventoryWriteRepository:
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqlitePlayerInventoryWriteRepository:
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成したリポジトリの書き込みは、アクティブなトランザクション内（with uow）で実行してください"
            )

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerInventoryAggregate]:
        row = self._conn.execute("SELECT * FROM game_player_inventories WHERE player_id = ?", (int(player_id),)).fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_inventory_from_row(row))

    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerInventoryAggregate]:
        return [x for pid in player_ids for x in [self.find_by_id(pid)] if x is not None]

    def save(self, inventory: PlayerInventoryAggregate) -> PlayerInventoryAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(inventory)
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        player_id = int(inventory.player_id)
        try:
            self._conn.execute(
                """
                INSERT INTO game_player_inventories (player_id, max_slots)
                VALUES (?, ?)
                ON CONFLICT(player_id) DO UPDATE SET max_slots = excluded.max_slots
                """,
                (player_id, inventory.max_slots),
            )
            for table_name in (
                "game_player_inventory_slots",
                "game_player_equipment_slots",
                "game_player_reserved_items",
            ):
                self._conn.execute(f"DELETE FROM {table_name} WHERE player_id = ?", (player_id,))
            self._conn.executemany(
                "INSERT INTO game_player_inventory_slots (player_id, slot_id, item_instance_id) VALUES (?, ?, ?)",
                [
                    (player_id, slot_id.value, None if item_id is None else int(item_id))
                    for slot_id, item_id in sorted(inventory._inventory_slots.items(), key=lambda x: x[0].value)
                ],
            )
            self._conn.executemany(
                "INSERT INTO game_player_equipment_slots (player_id, equipment_slot_type, item_instance_id) VALUES (?, ?, ?)",
                [
                    (player_id, slot_type.value, None if item_id is None else int(item_id))
                    for slot_type, item_id in sorted(inventory._equipment_slots.items(), key=lambda x: x[0].value)
                ],
            )
            self._conn.executemany(
                "INSERT INTO game_player_reserved_items (player_id, item_instance_id) VALUES (?, ?)",
                [(player_id, int(item_id)) for item_id in sorted(inventory.reserved_item_ids, key=int)],
            )
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return copy.deepcopy(inventory)

    def delete(self, player_id: PlayerId) -> bool:
        self._assert_shared_transaction_active()
        began_local_transaction = False
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.execute("BEGIN")
            began_local_transaction = True
        player_id_value = int(player_id)
        try:
            for table_name in ("game_player_inventory_slots", "game_player_equipment_slots", "game_player_reserved_items"):
                self._conn.execute(f"DELETE FROM {table_name} WHERE player_id = ?", (player_id_value,))
            cur = self._conn.execute("DELETE FROM game_player_inventories WHERE player_id = ?", (player_id_value,))
            if began_local_transaction:
                self._conn.commit()
            else:
                self._finalize_write()
        except Exception:
            if began_local_transaction and self._conn.in_transaction:
                self._conn.rollback()
            raise
        return cur.rowcount > 0

    def find_all(self) -> List[PlayerInventoryAggregate]:
        cur = self._conn.execute("SELECT * FROM game_player_inventories ORDER BY player_id ASC")
        return [copy.deepcopy(self._build_inventory_from_row(row)) for row in cur.fetchall()]

    def _build_inventory_from_row(self, row: sqlite3.Row) -> PlayerInventoryAggregate:
        player_id = int(row["player_id"])
        inventory_slot_rows = self._conn.execute(
            "SELECT slot_id, item_instance_id FROM game_player_inventory_slots WHERE player_id = ? ORDER BY slot_id ASC",
            (player_id,),
        ).fetchall()
        equipment_slot_rows = self._conn.execute(
            "SELECT equipment_slot_type, item_instance_id FROM game_player_equipment_slots WHERE player_id = ? ORDER BY equipment_slot_type ASC",
            (player_id,),
        ).fetchall()
        reserved_item_rows = self._conn.execute(
            "SELECT item_instance_id FROM game_player_reserved_items WHERE player_id = ? ORDER BY item_instance_id ASC",
            (player_id,),
        ).fetchall()
        return build_player_inventory(
            row=row,
            inventory_slot_rows=list(inventory_slot_rows),
            equipment_slot_rows=list(equipment_slot_rows),
            reserved_item_rows=list(reserved_item_rows),
        )


__all__ = ["SqlitePlayerInventoryWriteRepository"]
