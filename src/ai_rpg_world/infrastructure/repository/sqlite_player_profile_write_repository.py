"""プレイヤープロフィール集約の SQLite 実装（ゲーム書き込み DB）。"""
from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_trade_command_codec import (
    profile_to_row,
    row_to_profile,
)


class SqlitePlayerProfileWriteRepository(PlayerProfileRepository):
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
    ) -> SqlitePlayerProfileWriteRepository:
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> SqlitePlayerProfileWriteRepository:
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

    def generate_id(self) -> PlayerId:
        pid = PlayerId(allocate_sequence_value(self._conn, "player_id"))
        self._finalize_write()
        return pid

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerProfileAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_player_profiles WHERE player_id = ?",
            (int(player_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(row_to_profile(row))

    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerProfileAggregate]:
        return [p for pid in player_ids for p in [self.find_by_id(pid)] if p is not None]

    def find_by_name(self, name: PlayerName) -> Optional[PlayerProfileAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_player_profiles WHERE name = ?",
            (name.value,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(row_to_profile(row))

    def exists_name(self, name: PlayerName) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM game_player_profiles WHERE name = ? LIMIT 1",
            (name.value,),
        )
        return cur.fetchone() is not None

    def save(self, profile: PlayerProfileAggregate) -> PlayerProfileAggregate:
        self._maybe_emit_events(profile)
        row = profile_to_row(profile)
        self._conn.execute(
            """
            INSERT INTO game_player_profiles (
                player_id, name, role, race, element, control_type
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(player_id) DO UPDATE SET
                name = excluded.name,
                role = excluded.role,
                race = excluded.race,
                element = excluded.element,
                control_type = excluded.control_type
            """,
            row,
        )
        self._finalize_write()
        return copy.deepcopy(profile)

    def delete(self, player_id: PlayerId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_player_profiles WHERE player_id = ?",
            (int(player_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[PlayerProfileAggregate]:
        cur = self._conn.execute("SELECT * FROM game_player_profiles")
        return [copy.deepcopy(row_to_profile(r)) for r in cur.fetchall()]


__all__ = ["SqlitePlayerProfileWriteRepository"]
