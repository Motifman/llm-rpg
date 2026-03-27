"""プレイヤーインベントリ集約の SQLite 実装（ゲーム書き込み DB）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import init_game_write_schema
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_codec import (
    inventory_to_json,
    json_to_inventory,
)


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

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerInventoryAggregate]:
        cur = self._conn.execute(
            "SELECT payload_json FROM game_player_inventories WHERE player_id = ?",
            (int(player_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        inv = json_to_inventory(int(player_id), str(row["payload_json"]))
        return copy.deepcopy(inv)

    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerInventoryAggregate]:
        return [x for pid in player_ids for x in [self.find_by_id(pid)] if x is not None]

    def save(self, inventory: PlayerInventoryAggregate) -> PlayerInventoryAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(inventory)
        payload = inventory_to_json(inventory)
        pid = int(inventory.player_id)
        self._conn.execute(
            """
            INSERT INTO game_player_inventories (player_id, payload_json)
            VALUES (?, ?)
            ON CONFLICT(player_id) DO UPDATE SET payload_json = excluded.payload_json
            """,
            (pid, payload),
        )
        self._finalize_write()
        return copy.deepcopy(inventory)

    def delete(self, player_id: PlayerId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_player_inventories WHERE player_id = ?",
            (int(player_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[PlayerInventoryAggregate]:
        cur = self._conn.execute(
            "SELECT player_id, payload_json FROM game_player_inventories",
        )
        return [
            copy.deepcopy(json_to_inventory(int(r["player_id"]), str(r["payload_json"])))
            for r in cur.fetchall()
        ]


__all__ = ["SqlitePlayerInventoryWriteRepository"]
