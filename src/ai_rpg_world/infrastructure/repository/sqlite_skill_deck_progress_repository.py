"""SQLite implementation of skill deck progress aggregate repository."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.skill.aggregate.skill_deck_progress_aggregate import (
    SkillDeckProgressAggregate,
)
from ai_rpg_world.domain.skill.repository.skill_repository import (
    SkillDeckProgressRepository,
)
from ai_rpg_world.domain.skill.value_object.skill_deck_progress_id import (
    SkillDeckProgressId,
)
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_state_codec import (
    build_skill_deck_progress,
)


class SqliteSkillDeckProgressRepository(SkillDeckProgressRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteSkillDeckProgressRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteSkillDeckProgressRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def find_by_id(self, entity_id: SkillDeckProgressId) -> Optional[SkillDeckProgressAggregate]:
        cur = self._conn.execute(
            "SELECT * FROM game_skill_deck_progresses WHERE progress_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_progress_from_row(row)

    def find_by_ids(self, entity_ids: List[SkillDeckProgressId]) -> List[SkillDeckProgressAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillDeckProgressAggregate]:
        cur = self._conn.execute("SELECT * FROM game_skill_deck_progresses ORDER BY progress_id ASC")
        return [self._build_progress_from_row(row) for row in cur.fetchall()]

    def save(self, entity: SkillDeckProgressAggregate) -> SkillDeckProgressAggregate:
        self._conn.execute(
            """
            INSERT INTO game_skill_deck_progresses (
                progress_id, owner_id, deck_level, deck_exp,
                exp_table_base_exp, exp_table_exponent, exp_table_level_offset,
                capacity_growth_per_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(progress_id) DO UPDATE SET
                owner_id = excluded.owner_id,
                deck_level = excluded.deck_level,
                deck_exp = excluded.deck_exp,
                exp_table_base_exp = excluded.exp_table_base_exp,
                exp_table_exponent = excluded.exp_table_exponent,
                exp_table_level_offset = excluded.exp_table_level_offset,
                capacity_growth_per_level = excluded.capacity_growth_per_level
            """,
            (
                int(entity.progress_id),
                int(entity.owner_id),
                entity.deck_level,
                entity.deck_exp,
                entity._exp_table.base_exp,
                entity._exp_table.exponent,
                entity._exp_table.level_offset,
                entity._capacity_growth_per_level,
            ),
        )
        for table_name in (
            "game_skill_deck_progress_capacity_bonuses",
            "game_skill_deck_progress_proposals",
            "game_skill_deck_progress_proposal_required_skills",
        ):
            self._conn.execute(f"DELETE FROM {table_name} WHERE progress_id = ?", (int(entity.progress_id),))
        self._conn.executemany(
            """
            INSERT INTO game_skill_deck_progress_capacity_bonuses (
                progress_id, level, bonus_capacity
            ) VALUES (?, ?, ?)
            """,
            [
                (int(entity.progress_id), level, bonus)
                for level, bonus in sorted(entity._capacity_bonus_by_level.items())
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_deck_progress_proposals (
                progress_id, proposal_id, proposal_type, offered_skill_id,
                deck_tier, target_slot_index, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    int(entity.progress_id),
                    proposal.proposal_id,
                    proposal.proposal_type.value,
                    int(proposal.offered_skill_id),
                    proposal.deck_tier.value,
                    proposal.target_slot_index,
                    proposal.reason,
                )
                for proposal in entity.pending_proposals
            ],
        )
        self._conn.executemany(
            """
            INSERT INTO game_skill_deck_progress_proposal_required_skills (
                progress_id, proposal_id, required_index, skill_id
            ) VALUES (?, ?, ?, ?)
            """,
            [
                (
                    int(entity.progress_id),
                    proposal.proposal_id,
                    required_index,
                    int(required_skill_id),
                )
                for proposal in entity.pending_proposals
                for required_index, required_skill_id in enumerate(proposal.required_skill_ids)
            ],
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: SkillDeckProgressId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_skill_deck_progress_capacity_bonuses WHERE progress_id = ?",
            (int(entity_id),),
        )
        self._conn.execute(
            "DELETE FROM game_skill_deck_progress_proposal_required_skills WHERE progress_id = ?",
            (int(entity_id),),
        )
        self._conn.execute(
            "DELETE FROM game_skill_deck_progress_proposals WHERE progress_id = ?",
            (int(entity_id),),
        )
        cur = self._conn.execute(
            "DELETE FROM game_skill_deck_progresses WHERE progress_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0

    def find_by_owner_id(self, owner_id: int) -> SkillDeckProgressAggregate | None:
        cur = self._conn.execute(
            "SELECT * FROM game_skill_deck_progresses WHERE owner_id = ?",
            (owner_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._build_progress_from_row(row)

    def _build_progress_from_row(self, row: sqlite3.Row) -> SkillDeckProgressAggregate:
        capacity_rows = self._conn.execute(
            """
            SELECT level, bonus_capacity
            FROM game_skill_deck_progress_capacity_bonuses
            WHERE progress_id = ?
            ORDER BY level ASC
            """,
            (int(row["progress_id"]),),
        ).fetchall()
        proposal_rows = self._conn.execute(
            """
            SELECT *
            FROM game_skill_deck_progress_proposals
            WHERE progress_id = ?
            ORDER BY proposal_id ASC
            """,
            (int(row["progress_id"]),),
        ).fetchall()
        required_rows = self._conn.execute(
            """
            SELECT *
            FROM game_skill_deck_progress_proposal_required_skills
            WHERE progress_id = ?
            ORDER BY proposal_id ASC, required_index ASC
            """,
            (int(row["progress_id"]),),
        ).fetchall()
        return build_skill_deck_progress(
            row=row,
            capacity_bonus_rows=[
                (int(capacity_row["level"]), int(capacity_row["bonus_capacity"]))
                for capacity_row in capacity_rows
            ],
            proposal_rows=proposal_rows,
            required_skill_rows=required_rows,
        )


__all__ = ["SqliteSkillDeckProgressRepository"]
