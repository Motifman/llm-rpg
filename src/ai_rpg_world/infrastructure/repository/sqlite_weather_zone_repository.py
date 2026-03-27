"""SQLite implementation of `WeatherZoneRepository`."""

from __future__ import annotations

import sqlite3
from typing import Any, List, Optional

from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.repository.weather_zone_repository import (
    WeatherZoneRepository,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_weather_zone_state_codec import (
    build_weather_zone,
)


class SqliteWeatherZoneRepository(WeatherZoneRepository):
    """Store weather zones as snapshots with spot reverse index."""

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
    ) -> "SqliteWeatherZoneRepository":
        return cls(connection, _commits_after_write=True, event_sink=event_sink)

    @classmethod
    def for_shared_unit_of_work(
        cls,
        connection: sqlite3.Connection,
        *,
        event_sink: Any = None,
    ) -> "SqliteWeatherZoneRepository":
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

    def save(self, weather_zone: WeatherZone) -> WeatherZone:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(weather_zone)
        zone_id = int(weather_zone.zone_id)
        self._conn.execute(
            """
            INSERT INTO game_weather_zones (
                zone_id, name, weather_type, intensity
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(zone_id) DO UPDATE SET
                name = excluded.name,
                weather_type = excluded.weather_type,
                intensity = excluded.intensity
            """,
            (
                zone_id,
                weather_zone.name.value,
                weather_zone.current_state.weather_type.value,
                weather_zone.current_state.intensity,
            ),
        )
        self._conn.execute(
            "DELETE FROM game_weather_zone_spots WHERE zone_id = ?",
            (zone_id,),
        )
        self._conn.executemany(
            """
            INSERT INTO game_weather_zone_spots (spot_id, zone_id)
            VALUES (?, ?)
            ON CONFLICT(spot_id) DO UPDATE SET zone_id = excluded.zone_id
            """,
            [(int(spot_id), zone_id) for spot_id in sorted(weather_zone.spot_ids, key=int)],
        )
        self._finalize_write()
        return weather_zone

    def find_by_id(self, zone_id: WeatherZoneId) -> Optional[WeatherZone]:
        cur = self._conn.execute(
            "SELECT zone_id, name, weather_type, intensity FROM game_weather_zones WHERE zone_id = ?",
            (int(zone_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        spot_rows = self._conn.execute(
            "SELECT spot_id FROM game_weather_zone_spots WHERE zone_id = ? ORDER BY spot_id ASC",
            (int(zone_id),),
        ).fetchall()
        return build_weather_zone(
            zone_id=int(row["zone_id"]),
            name=row["name"],
            weather_type=row["weather_type"],
            intensity=float(row["intensity"]),
            spot_ids=[int(spot_row["spot_id"]) for spot_row in spot_rows],
        )

    def find_by_ids(self, zone_ids: List[WeatherZoneId]) -> List[WeatherZone]:
        return [x for zone_id in zone_ids for x in [self.find_by_id(zone_id)] if x is not None]

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[WeatherZone]:
        cur = self._conn.execute(
            "SELECT zone_id FROM game_weather_zone_spots WHERE spot_id = ?",
            (int(spot_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self.find_by_id(WeatherZoneId(int(row["zone_id"])))

    def find_all(self) -> List[WeatherZone]:
        cur = self._conn.execute(
            "SELECT zone_id FROM game_weather_zones ORDER BY zone_id ASC"
        )
        return [zone for row in cur.fetchall() for zone in [self.find_by_id(WeatherZoneId(int(row["zone_id"])))] if zone is not None]

    def delete(self, zone_id: WeatherZoneId) -> bool:
        self._assert_shared_transaction_active()
        self._conn.execute(
            "DELETE FROM game_weather_zone_spots WHERE zone_id = ?",
            (int(zone_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_weather_zones WHERE zone_id = ?",
            (int(zone_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteWeatherZoneRepository"]
