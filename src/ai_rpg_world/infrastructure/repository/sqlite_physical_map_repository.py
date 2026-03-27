"""SQLite implementation of `PhysicalMapRepository` for the single game DB."""

from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_world_state_codec import (
    blob_to_physical_map,
    physical_map_to_blob,
)


_WORLD_OBJECT_SEQUENCE_START = 99_999


class SqlitePhysicalMapRepository(PhysicalMapRepository):
    """Store physical maps as snapshots plus a relational object-location index."""

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
        self._backfill_gateway_connections_if_needed()

    @classmethod
    def for_standalone_connection(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqlitePhysicalMapRepository":
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqlitePhysicalMapRepository":
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

    def _backfill_gateway_connections_if_needed(self) -> None:
        cur = self._conn.execute("SELECT COUNT(*) FROM game_gateway_connections")
        gateway_count = int(cur.fetchone()[0])
        if gateway_count > 0:
            return

        cur = self._conn.execute("SELECT spot_id, aggregate_blob FROM game_physical_maps")
        rows = cur.fetchall()
        if not rows:
            return

        inserts: list[tuple[int, int]] = []
        for row in rows:
            physical_map = blob_to_physical_map(bytes(row["aggregate_blob"]))
            from_spot_id = int(physical_map.spot_id)
            for gateway in physical_map.get_all_gateways():
                inserts.append((from_spot_id, int(gateway.target_spot_id)))

        if not inserts:
            return

        self._conn.executemany(
            """
            INSERT INTO game_gateway_connections (from_spot_id, to_spot_id)
            VALUES (?, ?)
            ON CONFLICT(from_spot_id, to_spot_id) DO NOTHING
            """,
            inserts,
        )
        if self._commits_after_write and not self._conn.in_transaction:
            self._conn.commit()

    def generate_world_object_id(self) -> WorldObjectId:
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

    def find_by_id(self, entity_id: SpotId) -> Optional[PhysicalMapAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_physical_maps WHERE spot_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_physical_map(bytes(row["aggregate_blob"])))

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[PhysicalMapAggregate]:
        return self.find_by_id(spot_id)

    def find_by_ids(self, entity_ids: List[SpotId]) -> List[PhysicalMapAggregate]:
        return [x for spot_id in entity_ids for x in [self.find_by_id(spot_id)] if x is not None]

    def save(self, physical_map: PhysicalMapAggregate) -> PhysicalMapAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(physical_map)
        blob = physical_map_to_blob(physical_map)
        spot_id = int(physical_map.spot_id)
        self._conn.execute(
            """
            INSERT INTO game_physical_maps (spot_id, aggregate_blob)
            VALUES (?, ?)
            ON CONFLICT(spot_id) DO UPDATE SET aggregate_blob = excluded.aggregate_blob
            """,
            (spot_id, blob),
        )
        self._conn.execute(
            "DELETE FROM game_world_object_locations WHERE spot_id = ?",
            (spot_id,),
        )
        self._conn.execute(
            "DELETE FROM game_gateway_connections WHERE from_spot_id = ?",
            (spot_id,),
        )
        self._conn.executemany(
            """
            INSERT INTO game_world_object_locations (world_object_id, spot_id)
            VALUES (?, ?)
            ON CONFLICT(world_object_id) DO UPDATE SET spot_id = excluded.spot_id
            """,
            [
                (int(obj.object_id), spot_id)
                for obj in physical_map.get_all_objects()
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_gateway_connections (from_spot_id, to_spot_id)
            VALUES (?, ?)
            ON CONFLICT(from_spot_id, to_spot_id) DO NOTHING
            """,
            [
                (spot_id, int(gateway.target_spot_id))
                for gateway in physical_map.get_all_gateways()
            ],
        )
        self._finalize_write()
        return copy.deepcopy(physical_map)

    def delete(self, entity_id: SpotId) -> bool:
        self._assert_shared_transaction_active()
        self._conn.execute(
            "DELETE FROM game_world_object_locations WHERE spot_id = ?",
            (int(entity_id),),
        )
        self._conn.execute(
            "DELETE FROM game_gateway_connections WHERE from_spot_id = ?",
            (int(entity_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_physical_maps WHERE spot_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[PhysicalMapAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_physical_maps ORDER BY spot_id ASC"
        )
        return [
            copy.deepcopy(blob_to_physical_map(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]

    def find_spot_id_by_object_id(self, object_id: WorldObjectId) -> Optional[SpotId]:
        cur = self._conn.execute(
            "SELECT spot_id FROM game_world_object_locations WHERE world_object_id = ?",
            (int(object_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return SpotId(int(row["spot_id"]))

    def find_connected_spot_ids(self, spot_id: SpotId) -> List[SpotId]:
        cur = self._conn.execute(
            """
            SELECT to_spot_id
            FROM game_gateway_connections
            WHERE from_spot_id = ?
            ORDER BY to_spot_id ASC
            """,
            (int(spot_id),),
        )
        return [SpotId(int(row["to_spot_id"])) for row in cur.fetchall()]


__all__ = ["SqlitePhysicalMapRepository"]
