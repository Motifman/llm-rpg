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
    area_to_record_storage,
    build_physical_map,
    component_to_record_storage,
    trigger_to_record_storage,
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
        object_child_tables = (
            "game_physical_map_object_capabilities",
            "game_physical_map_object_chest_items",
            "game_physical_map_object_interaction_data",
            "game_physical_map_object_patrol_points",
            "game_physical_map_object_available_skills",
            "game_physical_map_object_threat_races",
            "game_physical_map_object_prey_races",
        )
        for table_name in object_child_tables:
            self._conn.execute(
                f"""
                DELETE FROM {table_name}
                WHERE world_object_id IN (
                    SELECT world_object_id FROM game_physical_map_objects WHERE spot_id = ?
                )
                """,
                (spot_id,),
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
        object_component_rows = [
            (
                int(obj.object_id),
                *component_to_record_storage(obj.component),
            )
            for obj in physical_map.get_all_objects()
        ]
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_objects (
                world_object_id, spot_id, x, y, z, object_type, is_blocking, is_blocking_sight,
                busy_until_tick, component_type,
                actor_direction, actor_speed_modifier, actor_player_id, actor_is_npc, actor_fov_angle,
                actor_race, actor_faction, actor_pack_id,
                autonomous_vision_range, autonomous_initial_x, autonomous_initial_y, autonomous_initial_z,
                autonomous_random_move_chance, autonomous_behavior_strategy_type, autonomous_is_pack_leader,
                autonomous_ecology_type, autonomous_ambush_chase_range, autonomous_territory_radius,
                autonomous_aggro_forget_after_ticks, autonomous_aggro_revenge_never_forget, autonomous_active_time,
                chest_is_open, door_is_open, door_is_locked, ground_item_instance_id,
                interactable_type, interactable_duration,
                placeable_item_spec_id, placeable_inner_type,
                placeable_trigger_type, placeable_trigger_warp_target_spot_id, placeable_trigger_warp_target_x,
                placeable_trigger_warp_target_y, placeable_trigger_warp_target_z, placeable_trigger_damage,
                harvest_loot_table_id, harvest_max_quantity, harvest_current_quantity, harvest_respawn_interval,
                harvest_last_update_tick, harvest_required_tool_category, harvest_duration, harvest_stamina_cost,
                harvest_current_actor_id, harvest_finish_tick
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    object_id,
                    spot_id,
                    obj.coordinate.x,
                    obj.coordinate.y,
                    obj.coordinate.z,
                    obj.object_type.value,
                    1 if obj.is_blocking else 0,
                    1 if obj.is_blocking_sight else 0,
                    None if obj.busy_until is None else obj.busy_until.value,
                    *component_parent_row,
                )
                for obj, (object_id, component_parent_row, _capability_rows, _chest_item_rows, _interaction_data_rows, _patrol_rows, _available_skill_rows, _threat_race_rows, _prey_race_rows) in zip(
                    physical_map.get_all_objects(), object_component_rows
                )
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_capabilities (world_object_id, capability_index, capability)
            VALUES (?, ?, ?)
            """,
            [
                (object_id, idx, capability)
                for object_id, _component_parent_row, capability_rows, _chest_item_rows, _interaction_data_rows, _patrol_rows, _available_skill_rows, _threat_race_rows, _prey_race_rows in object_component_rows
                for idx, capability in enumerate(capability_rows)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_chest_items (world_object_id, item_index, item_instance_id)
            VALUES (?, ?, ?)
            """,
            [
                (object_id, idx, item_instance_id)
                for object_id, _component_parent_row, _capability_rows, chest_item_rows, _interaction_data_rows, _patrol_rows, _available_skill_rows, _threat_race_rows, _prey_race_rows in object_component_rows
                for idx, item_instance_id in enumerate(chest_item_rows)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_interaction_data (
                world_object_id, data_key, value_type, value_text, value_integer, value_real, value_boolean
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    object_id,
                    data_key,
                    value_type,
                    None if value_type != "text" else value,
                    None if value_type != "int" else value,
                    None if value_type != "float" else value,
                    None if value_type != "bool" else value,
                )
                for object_id, _component_parent_row, _capability_rows, _chest_item_rows, interaction_data_rows, _patrol_rows, _available_skill_rows, _threat_race_rows, _prey_race_rows in object_component_rows
                for data_key, value_type, value in interaction_data_rows
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_patrol_points (world_object_id, point_index, x, y, z)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (object_id, idx, point.x, point.y, point.z)
                for object_id, _component_parent_row, _capability_rows, _chest_item_rows, _interaction_data_rows, patrol_rows, _available_skill_rows, _threat_race_rows, _prey_race_rows in object_component_rows
                for idx, point in enumerate(patrol_rows)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_available_skills (
                world_object_id, skill_index, slot_index, range, mp_cost
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (object_id, idx, skill.slot_index, skill.range, skill.mp_cost)
                for object_id, _component_parent_row, _capability_rows, _chest_item_rows, _interaction_data_rows, _patrol_rows, available_skill_rows, _threat_race_rows, _prey_race_rows in object_component_rows
                for idx, skill in enumerate(available_skill_rows)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_threat_races (world_object_id, race_index, race)
            VALUES (?, ?, ?)
            """,
            [
                (object_id, idx, race)
                for object_id, _component_parent_row, _capability_rows, _chest_item_rows, _interaction_data_rows, _patrol_rows, _available_skill_rows, threat_race_rows, _prey_race_rows in object_component_rows
                for idx, race in enumerate(threat_race_rows)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_object_prey_races (world_object_id, race_index, race)
            VALUES (?, ?, ?)
            """,
            [
                (object_id, idx, race)
                for object_id, _component_parent_row, _capability_rows, _chest_item_rows, _interaction_data_rows, _patrol_rows, _available_skill_rows, _threat_race_rows, prey_race_rows in object_component_rows
                for idx, race in enumerate(prey_race_rows)
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
                trigger_id, spot_id, name, is_active, area_kind,
                area_point_x, area_point_y, area_point_z,
                area_rect_min_x, area_rect_max_x, area_rect_min_y, area_rect_max_y, area_rect_min_z, area_rect_max_z,
                area_circle_center_x, area_circle_center_y, area_circle_center_z, area_circle_radius,
                trigger_type, trigger_warp_target_spot_id, trigger_warp_target_x, trigger_warp_target_y, trigger_warp_target_z, trigger_damage
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(trigger.trigger_id),
                    spot_id,
                    trigger.name,
                    1 if trigger.is_active else 0,
                    *area_to_record_storage(trigger.area),
                    *trigger_to_record_storage(trigger.trigger),
                )
                for trigger in physical_map.get_all_area_triggers()
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_location_areas (
                location_area_id, spot_id, name, description, is_active, area_kind,
                area_point_x, area_point_y, area_point_z,
                area_rect_min_x, area_rect_max_x, area_rect_min_y, area_rect_max_y, area_rect_min_z, area_rect_max_z,
                area_circle_center_x, area_circle_center_y, area_circle_center_z, area_circle_radius
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(location.location_id),
                    spot_id,
                    location.name,
                    location.description,
                    1 if location.is_active else 0,
                    *area_to_record_storage(location.area),
                )
                for location in physical_map.get_all_location_areas()
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_physical_map_gateways (
                gateway_id, spot_id, name, is_active, area_kind,
                area_point_x, area_point_y, area_point_z,
                area_rect_min_x, area_rect_max_x, area_rect_min_y, area_rect_max_y, area_rect_min_z, area_rect_max_z,
                area_circle_center_x, area_circle_center_y, area_circle_center_z, area_circle_radius,
                target_spot_id, landing_x, landing_y, landing_z
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(gateway.gateway_id),
                    spot_id,
                    gateway.name,
                    1 if gateway.is_active else 0,
                    *area_to_record_storage(gateway.area),
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
        for table_name in (
            "game_physical_map_object_capabilities",
            "game_physical_map_object_chest_items",
            "game_physical_map_object_interaction_data",
            "game_physical_map_object_patrol_points",
            "game_physical_map_object_available_skills",
            "game_physical_map_object_threat_races",
            "game_physical_map_object_prey_races",
        ):
            self._conn.execute(
                f"""
                DELETE FROM {table_name}
                WHERE world_object_id IN (
                    SELECT world_object_id FROM game_physical_map_objects WHERE spot_id = ?
                )
                """,
                (spot_id,),
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
        object_ids = [int(row["world_object_id"]) for row in object_rows]
        if object_ids:
            placeholders = ",".join("?" for _ in object_ids)
            capability_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_capabilities WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, capability_index ASC",
                object_ids,
            ).fetchall()
            chest_item_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_chest_items WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, item_index ASC",
                object_ids,
            ).fetchall()
            interaction_data_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_interaction_data WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, data_key ASC",
                object_ids,
            ).fetchall()
            patrol_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_patrol_points WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, point_index ASC",
                object_ids,
            ).fetchall()
            available_skill_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_available_skills WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, skill_index ASC",
                object_ids,
            ).fetchall()
            threat_race_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_threat_races WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, race_index ASC",
                object_ids,
            ).fetchall()
            prey_race_rows = self._conn.execute(
                f"SELECT * FROM game_physical_map_object_prey_races WHERE world_object_id IN ({placeholders}) ORDER BY world_object_id ASC, race_index ASC",
                object_ids,
            ).fetchall()
        else:
            capability_rows = []
            chest_item_rows = []
            interaction_data_rows = []
            patrol_rows = []
            available_skill_rows = []
            threat_race_rows = []
            prey_race_rows = []
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
            capability_rows=list(capability_rows),
            chest_item_rows=list(chest_item_rows),
            interaction_data_rows=list(interaction_data_rows),
            patrol_rows=list(patrol_rows),
            available_skill_rows=list(available_skill_rows),
            threat_race_rows=list(threat_race_rows),
            prey_race_rows=list(prey_race_rows),
        )


__all__ = ["SqlitePhysicalMapRepository"]
