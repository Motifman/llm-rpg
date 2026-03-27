"""アイテム集約の SQLite 実装（ゲーム書き込み DB）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.repository.item_repository import ItemRepository
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_codec import (
    item_aggregate_to_storage,
    storage_to_item_aggregate,
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
        if self._event_sink is not None and hasattr(self._event_sink, "is_in_transaction"):
            if self._event_sink.is_in_transaction():
                return
        self._conn.commit()

    def _maybe_emit_events(self, aggregate: Any) -> None:
        sink = self._event_sink
        if sink is None or not hasattr(sink, "add_events_from_aggregate"):
            return
        if hasattr(sink, "is_in_transaction") and not sink.is_in_transaction():
            return
        sink.add_events_from_aggregate(aggregate)

    def _row_to_aggregate(self, row: sqlite3.Row) -> ItemAggregate:
        return storage_to_item_aggregate(
            int(row["item_instance_id"]),
            int(row["item_spec_id"]),
            str(row["payload_json"]),
        )

    def _all_aggregates(self) -> List[ItemAggregate]:
        cur = self._conn.execute("SELECT * FROM game_items")
        return [copy.deepcopy(self._row_to_aggregate(r)) for r in cur.fetchall()]

    def generate_item_instance_id(self) -> ItemInstanceId:
        iid = ItemInstanceId(allocate_sequence_value(self._conn, "item_instance_id"))
        self._finalize_write()
        return iid

    def find_by_id(self, item_instance_id: ItemInstanceId) -> Optional[ItemAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_items WHERE item_instance_id = ?",
            (int(item_instance_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._row_to_aggregate(row))

    def find_by_ids(self, item_instance_ids: List[ItemInstanceId]) -> List[ItemAggregate]:
        return [x for iid in item_instance_ids for x in [self.find_by_id(iid)] if x is not None]

    def find_all(self) -> List[ItemAggregate]:
        return self._all_aggregates()

    def save(self, aggregate: ItemAggregate) -> ItemAggregate:
        self._maybe_emit_events(aggregate)
        iid, spec_id, payload = item_aggregate_to_storage(aggregate)
        self._conn.execute(
            """
            INSERT INTO game_items (item_instance_id, item_spec_id, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(item_instance_id) DO UPDATE SET
                item_spec_id = excluded.item_spec_id,
                payload_json = excluded.payload_json
            """,
            (iid, spec_id, payload),
        )
        self._finalize_write()
        return copy.deepcopy(aggregate)

    def delete(self, item_instance_id: ItemInstanceId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_items WHERE item_instance_id = ?",
            (int(item_instance_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_by_spec_id(self, item_spec_id: ItemSpecId) -> List[ItemAggregate]:
        target = int(item_spec_id)
        return [a for a in self._all_aggregates() if int(a.item_spec.item_spec_id) == target]

    def find_by_type(self, item_type: ItemType) -> List[ItemAggregate]:
        return [a for a in self._all_aggregates() if a.item_spec.item_type == item_type]

    def find_by_rarity(self, rarity: Rarity) -> List[ItemAggregate]:
        return [a for a in self._all_aggregates() if a.item_spec.rarity == rarity]

    def find_broken_items(self) -> List[ItemAggregate]:
        return [a for a in self._all_aggregates() if a.is_broken]

    def find_tradeable_items(self) -> List[ItemAggregate]:
        return [a for a in self._all_aggregates() if a.item_spec.item_type != ItemType.QUEST]

    def find_by_owner_id(self, owner_id: int) -> List[ItemAggregate]:
        return []


__all__ = ["SqliteItemWriteRepository"]
