"""SQLite implementation of `MonsterRepository` for the single game DB."""

from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_state_codec import (
    blob_to_monster,
    monster_to_blob,
)


_WORLD_OBJECT_SEQUENCE_START = 99_999


class SqliteMonsterAggregateRepository(MonsterRepository):
    """Store monsters as snapshots plus relational lookup columns."""

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
    ) -> "SqliteMonsterAggregateRepository":
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteMonsterAggregateRepository":
        return cls(connection, _commits_after_write=False, event_sink=event_sink)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

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

    def generate_monster_id(self) -> MonsterId:
        self._assert_shared_transaction_active()
        monster_id = MonsterId(allocate_sequence_value(self._conn, "monster_id"))
        self._finalize_write()
        return monster_id

    def generate_world_object_id_for_npc(self) -> WorldObjectId:
        self._assert_shared_transaction_active()
        world_object_id = WorldObjectId(
            allocate_sequence_value(
                self._conn,
                "world_object_id",
                initial_value=_WORLD_OBJECT_SEQUENCE_START,
            )
        )
        self._finalize_write()
        return world_object_id

    def find_by_id(self, entity_id: MonsterId) -> Optional[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monsters WHERE monster_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_monster(bytes(row["aggregate_blob"])))

    def find_by_ids(self, entity_ids: List[MonsterId]) -> List[MonsterAggregate]:
        return [x for monster_id in entity_ids for x in [self.find_by_id(monster_id)] if x is not None]

    def find_by_world_object_id(self, world_object_id: WorldObjectId) -> Optional[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monsters WHERE world_object_id = ?",
            (int(world_object_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_monster(bytes(row["aggregate_blob"])))

    def find_by_spot_id(self, spot_id: SpotId) -> List[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monsters WHERE spot_id = ? ORDER BY monster_id ASC",
            (int(spot_id),),
        )
        return [
            copy.deepcopy(blob_to_monster(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]

    def save(self, entity: MonsterAggregate) -> MonsterAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(entity)
        self._conn.execute(
            """
            INSERT INTO game_monsters (
                monster_id, world_object_id, spot_id, aggregate_blob
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(monster_id) DO UPDATE SET
                world_object_id = excluded.world_object_id,
                spot_id = excluded.spot_id,
                aggregate_blob = excluded.aggregate_blob
            """,
            (
                int(entity.monster_id),
                int(entity.world_object_id),
                int(entity.spot_id) if entity.spot_id is not None else None,
                monster_to_blob(entity),
            ),
        )
        self._finalize_write()
        return copy.deepcopy(entity)

    def delete(self, entity_id: MonsterId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_monsters WHERE monster_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[MonsterAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monsters ORDER BY monster_id ASC"
        )
        return [
            copy.deepcopy(blob_to_monster(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]


__all__ = ["SqliteMonsterAggregateRepository"]
