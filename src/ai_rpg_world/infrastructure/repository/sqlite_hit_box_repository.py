"""SQLite implementation of `HitBoxRepository` for the single game DB."""

from __future__ import annotations

import copy
import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_hit_box_state_codec import (
    blob_to_hit_box,
    hit_box_to_blob,
)


class SqliteHitBoxRepository(HitBoxRepository):
    """Store hit boxes as snapshots with spot/activity lookup columns."""

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
    ) -> "SqliteHitBoxRepository":
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteHitBoxRepository":
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

    def generate_id(self) -> HitBoxId:
        self._assert_shared_transaction_active()
        hit_box_id = HitBoxId(allocate_sequence_value(self._conn, "hit_box_id"))
        self._finalize_write()
        return hit_box_id

    def batch_generate_ids(self, count: int) -> List[HitBoxId]:
        self._assert_shared_transaction_active()
        hit_box_ids = [
            HitBoxId(allocate_sequence_value(self._conn, "hit_box_id"))
            for _ in range(count)
        ]
        self._finalize_write()
        return hit_box_ids

    def find_by_id(self, entity_id: HitBoxId) -> Optional[HitBoxAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_hit_boxes WHERE hit_box_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_hit_box(bytes(row["aggregate_blob"])))

    def find_by_ids(self, entity_ids: List[HitBoxId]) -> List[HitBoxAggregate]:
        return [
            x for hit_box_id in entity_ids for x in [self.find_by_id(hit_box_id)] if x is not None
        ]

    def save(self, entity: HitBoxAggregate) -> HitBoxAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(entity)
        self._conn.execute(
            """
            INSERT INTO game_hit_boxes (
                hit_box_id, spot_id, owner_id, is_active, aggregate_blob
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(hit_box_id) DO UPDATE SET
                spot_id = excluded.spot_id,
                owner_id = excluded.owner_id,
                is_active = excluded.is_active,
                aggregate_blob = excluded.aggregate_blob
            """,
            (
                int(entity.hit_box_id),
                int(entity.spot_id),
                int(entity.owner_id),
                1 if entity.is_active else 0,
                hit_box_to_blob(entity),
            ),
        )
        self._finalize_write()
        return copy.deepcopy(entity)

    def save_all(self, entities: List[HitBoxAggregate]) -> None:
        for entity in entities:
            self.save(entity)

    def delete(self, entity_id: HitBoxId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_hit_boxes WHERE hit_box_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[HitBoxAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_hit_boxes ORDER BY hit_box_id ASC"
        )
        return [
            copy.deepcopy(blob_to_hit_box(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]

    def find_active_by_spot_id(self, spot_id: SpotId) -> List[HitBoxAggregate]:
        cur = self._conn.execute(
            """
            SELECT aggregate_blob
            FROM game_hit_boxes
            WHERE spot_id = ? AND is_active = 1
            ORDER BY hit_box_id ASC
            """,
            (int(spot_id),),
        )
        return [
            copy.deepcopy(blob_to_hit_box(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]

    def find_by_spot_id(self, spot_id: SpotId) -> List[HitBoxAggregate]:
        cur = self._conn.execute(
            """
            SELECT aggregate_blob
            FROM game_hit_boxes
            WHERE spot_id = ?
            ORDER BY hit_box_id ASC
            """,
            (int(spot_id),),
        )
        return [
            copy.deepcopy(blob_to_hit_box(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]


__all__ = ["SqliteHitBoxRepository"]
