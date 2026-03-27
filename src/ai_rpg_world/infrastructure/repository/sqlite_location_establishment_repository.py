"""SQLite implementation of `LocationEstablishmentRepository`."""

from __future__ import annotations

import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.repository.location_establishment_repository import (
    LocationEstablishmentRepository,
)
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_location_establishment_state_codec import (
    build_location_establishment,
)


class SqliteLocationEstablishmentRepository(LocationEstablishmentRepository):
    """Store location establishments as snapshots with composite key columns."""

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
    ) -> "SqliteLocationEstablishmentRepository":
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteLocationEstablishmentRepository":
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

    def find_by_id(
        self, slot_id: LocationSlotId
    ) -> Optional[LocationEstablishmentAggregate]:
        cur = self._conn.execute(
            """
            SELECT spot_id, location_area_id, establishment_type, establishment_id
            FROM game_location_establishments
            WHERE spot_id = ? AND location_area_id = ?
            """,
            (int(slot_id.spot_id), int(slot_id.location_area_id)),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return build_location_establishment(
            spot_id=int(row["spot_id"]),
            location_area_id=int(row["location_area_id"]),
            establishment_type=row["establishment_type"],
            establishment_id=row["establishment_id"],
        )

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[LocationEstablishmentAggregate]:
        return self.find_by_id(LocationSlotId(spot_id=spot_id, location_area_id=location_area_id))

    def find_by_ids(
        self, slot_ids: List[LocationSlotId]
    ) -> List[LocationEstablishmentAggregate]:
        return [x for slot_id in slot_ids for x in [self.find_by_id(slot_id)] if x is not None]

    def save(
        self, slot: LocationEstablishmentAggregate
    ) -> LocationEstablishmentAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(slot)
        self._conn.execute(
            """
            INSERT INTO game_location_establishments (
                spot_id,
                location_area_id,
                establishment_type,
                establishment_id
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(spot_id, location_area_id) DO UPDATE SET
                establishment_type = excluded.establishment_type,
                establishment_id = excluded.establishment_id
            """,
            (
                int(slot.spot_id),
                int(slot.location_area_id),
                (
                    slot.establishment_type.value
                    if slot.establishment_type is not None
                    else None
                ),
                slot.establishment_id,
            ),
        )
        self._finalize_write()
        return slot

    def delete(self, slot_id: LocationSlotId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            """
            DELETE FROM game_location_establishments
            WHERE spot_id = ? AND location_area_id = ?
            """,
            (int(slot_id.spot_id), int(slot_id.location_area_id)),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[LocationEstablishmentAggregate]:
        cur = self._conn.execute(
            """
            SELECT spot_id, location_area_id, establishment_type, establishment_id
            FROM game_location_establishments
            ORDER BY spot_id ASC, location_area_id ASC
            """
        )
        return [
            build_location_establishment(
                spot_id=int(row["spot_id"]),
                location_area_id=int(row["location_area_id"]),
                establishment_type=row["establishment_type"],
                establishment_id=row["establishment_id"],
            )
            for row in cur.fetchall()
        ]


__all__ = ["SqliteLocationEstablishmentRepository"]
