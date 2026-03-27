"""SQLite implementation of `PhysicalMapRepository` for the single game DB."""

from __future__ import annotations

import copy
from typing import Any, List, Optional
import json
import sqlite3

from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    allocate_sequence_value,
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_world_state_codec import (
    area_to_storage,
    build_physical_map,
    component_to_storage,
    trigger_to_storage,
)


_WORLD_OBJECT_SEQUENCE_START = 99_999


class SqlitePhysicalMapRepository(PhysicalMapRepository):
    """Store physical maps in normalized child tables plus relational indexes."""

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
        rows = self._conn.execute(
            """
            SELECT DISTINCT spot_id, target_spot_id
            FROM game_physical_map_gateways
            ORDER BY spot_id ASC, target_spot_id ASC
            """
        ).fetchall()
        if not rows:
            return
        self._conn.executemany(
            """
            INSERT INTO game_gateway_connections (from_spot_id, to_spot_id)
            VALUES (?, ?)
            ON CONFLICT(from_spot_id, to_spot_id) DO NOTHING
            """,
            [(int(row["spot_id"]), int(row["target_spot_id"])) for row in rows],
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
            "SELECT * FROM game_physical_maps WHERE spot_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_physical_map_from_row(row))

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[PhysicalMapAggregate]:
        return self.find_by_id(spot_id)

    def find_by_ids(self, entity_ids: List[SpotId]) -> List[PhysicalMapAggregate]:
        return [x for spot_id in entity_ids for x in [self.find_by_id(spot_id)] if x is not None]

    def save(self, physical_map: PhysicalMapAggregate) -> PhysicalMapAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(physical_map)
        spot_id = int(physical_map.spot_id)
        self._conn.execute(
            """
            INSERT INTO game_physical_maps (
                spot_id, environment_type, weather_type, weather_intensity
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(spot_id) DO UPDATE SET
                environment_type = excluded.environment_type,
                weather_type = excluded.weather_type,
                weather_intensity = excluded.weather_intensity
            """,
            (
                spot_id,
                physical_map.environment_type.value,
                physical_map.weather_state.weather_type.value,
                physical_map.weather_state.intensity,
            ),
        )
        for table_name, key_column in (
            ("game_physical_map_area_traits", "spot_id"),
            ("game_physical_map_tiles", "spot_id"),
            ("game_physical_map_objects", "spot_id"),
            ("game_world_object_locations", "spot_id"),
            ("game_physical_map_area_triggers", "spot_id"),
            ("game_physical_map_location_areas", "spot_id"),
            ("game_physical_map_gateways", "spot_id"),
            ("game_gateway_connections", "from_spot_id"),
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE {key_column} = ?", (spot_id,))

        self._conn.executemany(
            """
            INSERT INTO game_physical_map_area_traits (spot_id, trait)
            VALUES (?, ?)
            """,
            [(spot_id, trait.value) for trait in sorted(physical_map.area_traits, key=lambda trait: trait.value)],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_tiles (
                spot_id, x, y, z, terrain_type, base_cost, required_capabilities_json,
                is_opaque, is_walkable_override
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    spot_id,
                    tile.coordinate.x,
                    tile.coordinate.y,
                    tile.coordinate.z,
                    tile.terrain_type.type.value,
                    tile.terrain_type.base_cost.value,
                    json.dumps(
                        sorted(cap.value for cap in tile.terrain_type.required_capabilities),
                        ensure_ascii=True,
                    ),
                    1 if tile.terrain_type.is_opaque else 0,
                    None if tile._is_walkable_override is None else (1 if tile._is_walkable_override else 0),
                )
                for tile in sorted(
                    physical_map.get_all_tiles(),
                    key=lambda tile: (tile.coordinate.z, tile.coordinate.y, tile.coordinate.x),
                )
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_objects (
                world_object_id, spot_id, x, y, z, object_type, is_blocking, is_blocking_sight,
                busy_until_tick, component_type, component_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(obj.object_id),
                    spot_id,
                    obj.coordinate.x,
                    obj.coordinate.y,
                    obj.coordinate.z,
                    obj.object_type.value,
                    1 if obj.is_blocking else 0,
                    1 if obj.is_blocking_sight else 0,
                    None if obj.busy_until is None else obj.busy_until.value,
                    *component_to_storage(obj.component),
                )
                for obj in physical_map.get_all_objects()
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_world_object_locations (world_object_id, spot_id)
            VALUES (?, ?)
            ON CONFLICT(world_object_id) DO UPDATE SET spot_id = excluded.spot_id
            """,
            [(int(obj.object_id), spot_id) for obj in physical_map.get_all_objects()],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_area_triggers (
                trigger_id, spot_id, name, is_active, area_kind, area_payload_json,
                trigger_type, trigger_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(trigger.trigger_id),
                    spot_id,
                    trigger.name,
                    1 if trigger.is_active else 0,
                    *area_to_storage(trigger.area),
                    *trigger_to_storage(trigger.trigger),
                )
                for trigger in physical_map.get_all_area_triggers()
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_location_areas (
                location_area_id, spot_id, name, description, is_active, area_kind, area_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(location.location_id),
                    spot_id,
                    location.name,
                    location.description,
                    1 if location.is_active else 0,
                    *area_to_storage(location.area),
                )
                for location in physical_map.get_all_location_areas()
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_gateways (
                gateway_id, spot_id, name, is_active, area_kind, area_payload_json,
                target_spot_id, landing_x, landing_y, landing_z
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(gateway.gateway_id),
                    spot_id,
                    gateway.name,
                    1 if gateway.is_active else 0,
                    *area_to_storage(gateway.area),
                    int(gateway.target_spot_id),
                    gateway.landing_coordinate.x,
                    gateway.landing_coordinate.y,
                    gateway.landing_coordinate.z,
                )
                for gateway in physical_map.get_all_gateways()
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
        spot_id = int(entity_id)
        for table_name, key_column in (
            ("game_physical_map_area_traits", "spot_id"),
            ("game_physical_map_tiles", "spot_id"),
            ("game_physical_map_objects", "spot_id"),
            ("game_world_object_locations", "spot_id"),
            ("game_physical_map_area_triggers", "spot_id"),
            ("game_physical_map_location_areas", "spot_id"),
            ("game_physical_map_gateways", "spot_id"),
            ("game_gateway_connections", "from_spot_id"),
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE {key_column} = ?", (spot_id,))
        cur = self._conn.execute(
            "DELETE FROM game_physical_maps WHERE spot_id = ?",
            (spot_id,),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[PhysicalMapAggregate]:
        cur = self._conn.execute("SELECT spot_id FROM game_physical_maps ORDER BY spot_id ASC")
        return [
            aggregate
            for row in cur.fetchall()
            for aggregate in [self.find_by_id(SpotId(int(row["spot_id"])))]
            if aggregate is not None
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

    def _build_physical_map_from_row(self, row: sqlite3.Row) -> PhysicalMapAggregate:
        spot_id = int(row["spot_id"])
        tile_rows = self._conn.execute(
            "SELECT * FROM game_physical_map_tiles WHERE spot_id = ? ORDER BY z ASC, y ASC, x ASC",
            (spot_id,),
        ).fetchall()
        object_rows = self._conn.execute(
            "SELECT * FROM game_physical_map_objects WHERE spot_id = ? ORDER BY world_object_id ASC",
            (spot_id,),
        ).fetchall()
        area_trigger_rows = self._conn.execute(
            "SELECT * FROM game_physical_map_area_triggers WHERE spot_id = ? ORDER BY trigger_id ASC",
            (spot_id,),
        ).fetchall()
        location_area_rows = self._conn.execute(
            "SELECT * FROM game_physical_map_location_areas WHERE spot_id = ? ORDER BY location_area_id ASC",
            (spot_id,),
        ).fetchall()
        gateway_rows = self._conn.execute(
            "SELECT * FROM game_physical_map_gateways WHERE spot_id = ? ORDER BY gateway_id ASC",
            (spot_id,),
        ).fetchall()
        area_trait_rows = self._conn.execute(
            "SELECT trait FROM game_physical_map_area_traits WHERE spot_id = ? ORDER BY trait ASC",
            (spot_id,),
        ).fetchall()
        return build_physical_map(
            row=row,
            tile_rows=list(tile_rows),
            object_rows=list(object_rows),
            area_trigger_rows=list(area_trigger_rows),
            location_area_rows=list(location_area_rows),
            gateway_rows=list(gateway_rows),
            area_trait_rows=[str(area_trait_row["trait"]) for area_trait_row in area_trait_rows],
        )


__all__ = ["SqlitePhysicalMapRepository"]
