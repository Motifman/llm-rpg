"""SQLite implementation of skill spec read repository and writer."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillSpecRepository,
    SkillSpecWriter,
)
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_state_codec import build_skill_spec


class SqliteSkillSpecRepository(SkillSpecRepository):
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteSkillSpecRepository":
        return cls(connection)

    def find_by_id(self, entity_id: SkillId) -> Optional[SkillSpec]:
        cur = self._conn.execute(
            "SELECT * FROM game_skill_specs WHERE skill_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_spec_from_row(row)

    def find_by_ids(self, entity_ids: List[SkillId]) -> List[SkillSpec]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillSpec]:
        cur = self._conn.execute("SELECT * FROM game_skill_specs ORDER BY skill_id ASC")
        return [self._build_spec_from_row(row) for row in cur.fetchall()]

    def _build_spec_from_row(self, row: sqlite3.Row) -> SkillSpec:
        required_rows = self._conn.execute(
            """
            SELECT required_skill_id
            FROM game_skill_spec_required_skills
            WHERE skill_id = ?
            ORDER BY required_index ASC
            """,
            (int(row["skill_id"]),),
        ).fetchall()
        race_rows = self._conn.execute(
            """
            SELECT race
            FROM game_skill_spec_slayer_races
            WHERE skill_id = ?
            ORDER BY race_index ASC
            """,
            (int(row["skill_id"]),),
        ).fetchall()
        effect_rows = self._conn.execute(
            """
            SELECT effect_type, duration_ticks, intensity, chance
            FROM game_skill_spec_hit_effects
            WHERE skill_id = ?
            ORDER BY effect_index ASC
            """,
            (int(row["skill_id"]),),
        ).fetchall()
        segment_rows = self._conn.execute(
            """
            SELECT *
            FROM game_skill_spec_hit_pattern_segments
            WHERE skill_id = ?
            ORDER BY segment_index ASC
            """,
            (int(row["skill_id"]),),
        ).fetchall()
        coord_rows = self._conn.execute(
            """
            SELECT *
            FROM game_skill_spec_hit_pattern_coords
            WHERE skill_id = ?
            ORDER BY segment_index ASC, coord_index ASC
            """,
            (int(row["skill_id"]),),
        ).fetchall()
        return build_skill_spec(
            row=row,
            required_skill_rows=[int(required_row["required_skill_id"]) for required_row in required_rows],
            slayer_race_rows=[race_row["race"] for race_row in race_rows],
            hit_effect_rows=[
                (
                    effect_row["effect_type"],
                    int(effect_row["duration_ticks"]),
                    float(effect_row["intensity"]),
                    float(effect_row["chance"]),
                )
                for effect_row in effect_rows
            ],
            segment_rows=segment_rows,
            coordinate_rows=coord_rows,
        )


class SqliteSkillSpecWriter(SkillSpecWriter):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteSkillSpecWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteSkillSpecWriter":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def _assert_shared_transaction_active(self) -> None:
        if self._commits_after_write:
            return
        if not self._conn.in_transaction:
            raise RuntimeError(
                "for_shared_unit_of_work で生成した writer の書き込みは、"
                "アクティブなトランザクション内（with uow）で実行してください"
            )

    def replace_spec(self, spec: SkillSpec) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_skill_specs (
                skill_id, name, element, deck_cost, cast_lock_ticks,
                cooldown_ticks, power_multiplier, pattern_type, mp_cost,
                stamina_cost, hp_cost, is_awakened_deck_only, targeting_range
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                name = excluded.name,
                element = excluded.element,
                deck_cost = excluded.deck_cost,
                cast_lock_ticks = excluded.cast_lock_ticks,
                cooldown_ticks = excluded.cooldown_ticks,
                power_multiplier = excluded.power_multiplier,
                pattern_type = excluded.pattern_type,
                mp_cost = excluded.mp_cost,
                stamina_cost = excluded.stamina_cost,
                hp_cost = excluded.hp_cost,
                is_awakened_deck_only = excluded.is_awakened_deck_only,
                targeting_range = excluded.targeting_range
            """,
            (
                int(spec.skill_id),
                spec.name,
                spec.element.value,
                spec.deck_cost,
                spec.cast_lock_ticks,
                spec.cooldown_ticks,
                spec.power_multiplier,
                spec.hit_pattern.pattern_type.value,
                spec.mp_cost,
                spec.stamina_cost,
                spec.hp_cost,
                int(spec.is_awakened_deck_only),
                spec.targeting_range,
            ),
        )
        for table_name in (
            "game_skill_spec_required_skills",
            "game_skill_spec_slayer_races",
            "game_skill_spec_hit_effects",
            "game_skill_spec_hit_pattern_segments",
            "game_skill_spec_hit_pattern_coords",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE skill_id = ?", (int(spec.skill_id),))
        self._conn.executemany(
            """
            INSERT INTO game_skill_spec_required_skills (
                skill_id, required_index, required_skill_id
            ) VALUES (?, ?, ?)
            """,
            [
                (int(spec.skill_id), index, int(required_skill_id))
                for index, required_skill_id in enumerate(spec.required_skill_ids)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_spec_slayer_races (
                skill_id, race_index, race
            ) VALUES (?, ?, ?)
            """,
            [
                (int(spec.skill_id), index, race.value)
                for index, race in enumerate(spec.slayer_races)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_spec_hit_effects (
                skill_id, effect_index, effect_type, duration_ticks, intensity, chance
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(spec.skill_id),
                    index,
                    effect.effect_type.value,
                    effect.duration_ticks,
                    effect.intensity,
                    effect.chance,
                )
                for index, effect in enumerate(spec.hit_effects)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_spec_hit_pattern_segments (
                skill_id, segment_index, start_offset_ticks, duration_ticks,
                velocity_dx, velocity_dy, velocity_dz,
                spawn_dx, spawn_dy, spawn_dz, segment_power_multiplier
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(spec.skill_id),
                    segment_index,
                    segment.start_offset_ticks,
                    segment.duration_ticks,
                    segment.velocity.dx,
                    segment.velocity.dy,
                    segment.velocity.dz,
                    segment.spawn_offset.dx,
                    segment.spawn_offset.dy,
                    segment.spawn_offset.dz,
                    segment.segment_power_multiplier,
                )
                for segment_index, segment in enumerate(spec.hit_pattern.timeline_segments)
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_spec_hit_pattern_coords (
                skill_id, segment_index, coord_index, dx, dy, dz
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(spec.skill_id),
                    segment_index,
                    coord_index,
                    coordinate.dx,
                    coordinate.dy,
                    coordinate.dz,
                )
                for segment_index, segment in enumerate(spec.hit_pattern.timeline_segments)
                for coord_index, coordinate in enumerate(segment.shape.relative_coordinates)
            ],
        )
        self._finalize_write()

    def delete_spec(self, skill_id: SkillId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_skill_spec_required_skills WHERE skill_id = ?",
            (int(skill_id),),
        )
        self._conn.execute("DELETE FROM game_skill_spec_slayer_races WHERE skill_id = ?", (int(skill_id),))
        self._conn.execute("DELETE FROM game_skill_spec_hit_effects WHERE skill_id = ?", (int(skill_id),))
        self._conn.execute("DELETE FROM game_skill_spec_hit_pattern_segments WHERE skill_id = ?", (int(skill_id),))
        self._conn.execute("DELETE FROM game_skill_spec_hit_pattern_coords WHERE skill_id = ?", (int(skill_id),))
        cur = self._conn.execute(
            "DELETE FROM game_skill_specs WHERE skill_id = ?",
            (int(skill_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteSkillSpecRepository", "SqliteSkillSpecWriter"]
