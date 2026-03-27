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
    build_hit_box,
)


class SqliteHitBoxRepository(HitBoxRepository):
    """Store hit boxes in normalized tables with spot/activity lookup columns."""

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
            "SELECT * FROM game_hit_boxes WHERE hit_box_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(self._build_hit_box_from_row(row))

    def find_by_ids(self, entity_ids: List[HitBoxId]) -> List[HitBoxAggregate]:
        return [
            x for hit_box_id in entity_ids for x in [self.find_by_id(hit_box_id)] if x is not None
        ]

    def save(self, entity: HitBoxAggregate) -> HitBoxAggregate:
        self._assert_shared_transaction_active()
        self._maybe_emit_events(entity)
        capabilities = ",".join(sorted(cap.value for cap in entity.movement_capability.capabilities))
        self._conn.execute(
            """
            INSERT INTO game_hit_boxes (
                hit_box_id, spot_id, owner_id, is_active,
                current_x, current_y, current_z,
                previous_x, previous_y, previous_z,
                precise_x, precise_y, precise_z,
                start_tick, duration, power_multiplier,
                velocity_dx, velocity_dy, velocity_dz,
                attacker_max_hp, attacker_max_mp, attacker_attack, attacker_defense,
                attacker_speed, attacker_critical_rate, attacker_evasion_rate,
                target_collision_policy, obstacle_collision_policy,
                movement_capabilities, movement_speed_modifier,
                activation_tick, skill_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hit_box_id) DO UPDATE SET
                spot_id = excluded.spot_id,
                owner_id = excluded.owner_id,
                is_active = excluded.is_active,
                current_x = excluded.current_x,
                current_y = excluded.current_y,
                current_z = excluded.current_z,
                previous_x = excluded.previous_x,
                previous_y = excluded.previous_y,
                previous_z = excluded.previous_z,
                precise_x = excluded.precise_x,
                precise_y = excluded.precise_y,
                precise_z = excluded.precise_z,
                start_tick = excluded.start_tick,
                duration = excluded.duration,
                power_multiplier = excluded.power_multiplier,
                velocity_dx = excluded.velocity_dx,
                velocity_dy = excluded.velocity_dy,
                velocity_dz = excluded.velocity_dz,
                attacker_max_hp = excluded.attacker_max_hp,
                attacker_max_mp = excluded.attacker_max_mp,
                attacker_attack = excluded.attacker_attack,
                attacker_defense = excluded.attacker_defense,
                attacker_speed = excluded.attacker_speed,
                attacker_critical_rate = excluded.attacker_critical_rate,
                attacker_evasion_rate = excluded.attacker_evasion_rate,
                target_collision_policy = excluded.target_collision_policy,
                obstacle_collision_policy = excluded.obstacle_collision_policy,
                movement_capabilities = excluded.movement_capabilities,
                movement_speed_modifier = excluded.movement_speed_modifier,
                activation_tick = excluded.activation_tick,
                skill_id = excluded.skill_id
            """,
            (
                int(entity.hit_box_id),
                int(entity.spot_id),
                int(entity.owner_id),
                1 if entity.is_active else 0,
                entity.current_coordinate.x,
                entity.current_coordinate.y,
                entity.current_coordinate.z,
                entity._previous_coordinate.x,
                entity._previous_coordinate.y,
                entity._previous_coordinate.z,
                entity.precise_position[0],
                entity.precise_position[1],
                entity.precise_position[2],
                entity._start_tick.value,
                entity._duration,
                entity.power_multiplier,
                entity.velocity.dx,
                entity.velocity.dy,
                entity.velocity.dz,
                None if entity.attacker_stats is None else entity.attacker_stats.max_hp,
                None if entity.attacker_stats is None else entity.attacker_stats.max_mp,
                None if entity.attacker_stats is None else entity.attacker_stats.attack,
                None if entity.attacker_stats is None else entity.attacker_stats.defense,
                None if entity.attacker_stats is None else entity.attacker_stats.speed,
                None if entity.attacker_stats is None else entity.attacker_stats.critical_rate,
                None if entity.attacker_stats is None else entity.attacker_stats.evasion_rate,
                entity._target_collision_policy.value,
                entity._obstacle_collision_policy.value,
                capabilities,
                entity.movement_capability.speed_modifier,
                entity.activation_tick,
                entity.skill_id,
            ),
        )
        hit_box_id = int(entity.hit_box_id)
        for table_name in (
            "game_hit_box_shape_coordinates",
            "game_hit_box_effects",
            "game_hit_box_targets",
            "game_hit_box_obstacle_coordinates",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE hit_box_id = ?", (hit_box_id,))
        self._conn.executemany(
            """
            INSERT INTO game_hit_box_shape_coordinates (
                hit_box_id, coordinate_index, dx, dy, dz
            ) VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    hit_box_id,
                    index,
                    rel.dx,
                    rel.dy,
                    rel.dz,
                )
                for index, rel in enumerate(entity._shape.relative_coordinates)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_hit_box_effects (
                hit_box_id, effect_index, effect_type, duration_ticks, intensity, chance
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    hit_box_id,
                    index,
                    effect.effect_type.value,
                    effect.duration_ticks,
                    effect.intensity,
                    effect.chance,
                )
                for index, effect in enumerate(entity.hit_effects)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_hit_box_targets (hit_box_id, target_id)
            VALUES (?, ?)
            """,
            [(hit_box_id, int(target_id)) for target_id in sorted(entity._hit_targets, key=int)],
        )
        self._conn.executemany(
            """
            INSERT INTO game_hit_box_obstacle_coordinates (hit_box_id, x, y, z)
            VALUES (?, ?, ?, ?)
            """,
            [
                (hit_box_id, coordinate.x, coordinate.y, coordinate.z)
                for coordinate in sorted(
                    entity._hit_obstacle_coordinates,
                    key=lambda coordinate: (coordinate.z, coordinate.y, coordinate.x),
                )
            ],
        )
        self._finalize_write()
        return copy.deepcopy(entity)

    def save_all(self, entities: List[HitBoxAggregate]) -> None:
        for entity in entities:
            self.save(entity)

    def delete(self, entity_id: HitBoxId) -> bool:
        self._assert_shared_transaction_active()
        hit_box_id = int(entity_id)
        for table_name in (
            "game_hit_box_shape_coordinates",
            "game_hit_box_effects",
            "game_hit_box_targets",
            "game_hit_box_obstacle_coordinates",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE hit_box_id = ?", (hit_box_id,))
        cur = self._conn.execute(
            "DELETE FROM game_hit_boxes WHERE hit_box_id = ?",
            (hit_box_id,),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_all(self) -> List[HitBoxAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_hit_boxes ORDER BY hit_box_id ASC"
        )
        return [copy.deepcopy(self._build_hit_box_from_row(row)) for row in cur.fetchall()]

    def find_active_by_spot_id(self, spot_id: SpotId) -> List[HitBoxAggregate]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_hit_boxes
            WHERE spot_id = ? AND is_active = 1
            ORDER BY hit_box_id ASC
            """,
            (int(spot_id),),
        )
        return [copy.deepcopy(self._build_hit_box_from_row(row)) for row in cur.fetchall()]

    def find_by_spot_id(self, spot_id: SpotId) -> List[HitBoxAggregate]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM game_hit_boxes
            WHERE spot_id = ?
            ORDER BY hit_box_id ASC
            """,
            (int(spot_id),),
        )
        return [copy.deepcopy(self._build_hit_box_from_row(row)) for row in cur.fetchall()]

    def _build_hit_box_from_row(self, row: sqlite3.Row) -> HitBoxAggregate:
        hit_box_id = int(row["hit_box_id"])
        shape_rows = self._conn.execute(
            """
            SELECT dx, dy, dz
            FROM game_hit_box_shape_coordinates
            WHERE hit_box_id = ?
            ORDER BY coordinate_index ASC
            """,
            (hit_box_id,),
        ).fetchall()
        effect_rows = self._conn.execute(
            """
            SELECT effect_type, duration_ticks, intensity, chance
            FROM game_hit_box_effects
            WHERE hit_box_id = ?
            ORDER BY effect_index ASC
            """,
            (hit_box_id,),
        ).fetchall()
        hit_target_rows = self._conn.execute(
            """
            SELECT target_id
            FROM game_hit_box_targets
            WHERE hit_box_id = ?
            ORDER BY target_id ASC
            """,
            (hit_box_id,),
        ).fetchall()
        obstacle_rows = self._conn.execute(
            """
            SELECT x, y, z
            FROM game_hit_box_obstacle_coordinates
            WHERE hit_box_id = ?
            ORDER BY z ASC, y ASC, x ASC
            """,
            (hit_box_id,),
        ).fetchall()
        return build_hit_box(
            row=row,
            shape_rows=list(shape_rows),
            effect_rows=list(effect_rows),
            hit_target_rows=[int(target_row["target_id"]) for target_row in hit_target_rows],
            obstacle_rows=list(obstacle_rows),
        )


__all__ = ["SqliteHitBoxRepository"]
