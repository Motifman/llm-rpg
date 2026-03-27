"""SQLite implementation of skill loadout aggregate repository."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.repository.skill_repository import SkillLoadoutRepository
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_spec_repository import SqliteSkillSpecRepository
from ai_rpg_world.infrastructure.repository.sqlite_skill_state_codec import build_skill_loadout


class SqliteSkillLoadoutRepository(SkillLoadoutRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteSkillLoadoutRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteSkillLoadoutRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def find_by_id(self, entity_id: SkillLoadoutId) -> Optional[SkillLoadoutAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_skill_loadouts WHERE loadout_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_loadout_from_row(row)

    def find_by_ids(self, entity_ids: List[SkillLoadoutId]) -> List[SkillLoadoutAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillLoadoutAggregate]:
        cur = self._conn.execute("SELECT * FROM game_skill_loadouts ORDER BY loadout_id ASC")
        return [self._build_loadout_from_row(row) for row in cur.fetchall()]

    def save(self, entity: SkillLoadoutAggregate) -> SkillLoadoutAggregate:
        self._conn.execute(
            """
            INSERT INTO game_skill_loadouts (
                loadout_id, owner_id, normal_capacity, awakened_capacity,
                awaken_is_active, awaken_active_until_tick,
                awaken_cooldown_reduction_rate, cast_lock_until_tick
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(loadout_id) DO UPDATE SET
                owner_id = excluded.owner_id,
                normal_capacity = excluded.normal_capacity,
                awakened_capacity = excluded.awakened_capacity,
                awaken_is_active = excluded.awaken_is_active,
                awaken_active_until_tick = excluded.awaken_active_until_tick,
                awaken_cooldown_reduction_rate = excluded.awaken_cooldown_reduction_rate,
                cast_lock_until_tick = excluded.cast_lock_until_tick
            """,
            (
                int(entity.loadout_id),
                int(entity.owner_id),
                entity.normal_deck.capacity,
                entity.awakened_deck.capacity,
                int(entity.awaken_state.is_active),
                entity.awaken_state.active_until_tick,
                entity.awaken_state.cooldown_reduction_rate,
                entity.cast_lock_until_tick,
            ),
        )
        self._conn.execute("DELETE FROM game_skill_loadout_slots WHERE loadout_id = ?", (int(entity.loadout_id),))
        self._conn.execute("DELETE FROM game_skill_loadout_cooldowns WHERE loadout_id = ?", (int(entity.loadout_id),))
        self._conn.executemany(
            """
            INSERT INTO game_skill_loadout_slots (
                loadout_id, deck_tier, slot_index, skill_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (int(entity.loadout_id), deck_tier, slot_index, int(skill.skill_id))
                for deck_tier, deck in (
                    (entity.normal_deck.deck_tier.value, entity.normal_deck),
                    (entity.awakened_deck.deck_tier.value, entity.awakened_deck),
                )
                for slot_index, skill in enumerate(deck.slots)
                if skill is not None
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_loadout_cooldowns (
                loadout_id, skill_id, ready_at_tick
            ) VALUES (?, ?, ?)
            """,
            [
                (int(entity.loadout_id), skill_id, ready_at_tick)
                for skill_id, ready_at_tick in sorted(entity._skill_cooldowns_until.items())
            ],
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: SkillLoadoutId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_skill_loadout_slots WHERE loadout_id = ?",
            (int(entity_id),),
        )
        self._conn.execute(
            "DELETE FROM game_skill_loadout_cooldowns WHERE loadout_id = ?",
            (int(entity_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_skill_loadouts WHERE loadout_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_by_owner_id(self, owner_id: int) -> SkillLoadoutAggregate | None:
        cur = self._conn.execute(
            "SELECT * FROM game_skill_loadouts WHERE owner_id = ?",
            (owner_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_loadout_from_row(row)

    def _build_loadout_from_row(self, row: sqlite3.Row) -> SkillLoadoutAggregate:
        slot_rows = self._conn.execute(
            """
            SELECT deck_tier, slot_index, skill_id
            FROM game_skill_loadout_slots
            WHERE loadout_id = ?
            ORDER BY deck_tier ASC, slot_index ASC
            """,
            (int(row["loadout_id"]),),
        ).fetchall()
        cooldown_rows = self._conn.execute(
            """
            SELECT skill_id, ready_at_tick
            FROM game_skill_loadout_cooldowns
            WHERE loadout_id = ?
            ORDER BY skill_id ASC
            """,
            (int(row["loadout_id"]),),
        ).fetchall()
        spec_repo = SqliteSkillSpecRepository.for_connection(self._conn)
        skill_specs_by_id = {}
        for slot_row in slot_rows:
            skill_id = int(slot_row["skill_id"])
            if skill_id in skill_specs_by_id:
                continue
            spec = spec_repo.find_by_id(SkillId(skill_id))
            if spec is None:
                raise RuntimeError(
                    "game_skill_loadout_slots が参照する skill_id に対応する "
                    "game_skill_specs の定義が見つかりません"
                )
            skill_specs_by_id[skill_id] = spec
        return build_skill_loadout(
            row=row,
            slot_rows=slot_rows,
            cooldown_rows=[(int(cd_row["skill_id"]), int(cd_row["ready_at_tick"])) for cd_row in cooldown_rows],
            skill_specs_by_id=skill_specs_by_id,
        )


__all__ = ["SqliteSkillLoadoutRepository"]
