"""SQLite implementation of skill spec read repository and writer."""

from __future__ import annotations

import copy
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
from ai_rpg_world.infrastructure.repository.sqlite_pickle_codec import (
    blob_to_object,
    object_to_blob,
)


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
            "SELECT aggregate_blob FROM game_skill_specs WHERE skill_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_object(bytes(row["aggregate_blob"])))

    def find_by_ids(self, entity_ids: List[SkillId]) -> List[SkillSpec]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[SkillSpec]:
        cur = self._conn.execute("SELECT aggregate_blob FROM game_skill_specs ORDER BY skill_id ASC")
        return [copy.deepcopy(blob_to_object(bytes(row["aggregate_blob"]))) for row in cur.fetchall()]


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
            INSERT INTO game_skill_specs (skill_id, name, aggregate_blob)
            VALUES (?, ?, ?)
            ON CONFLICT(skill_id) DO UPDATE SET
                name = excluded.name,
                aggregate_blob = excluded.aggregate_blob
            """,
            (int(spec.skill_id), spec.name, object_to_blob(spec)),
        )
        self._finalize_write()

    def delete_spec(self, skill_id: SkillId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_skill_specs WHERE skill_id = ?",
            (int(skill_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteSkillSpecRepository", "SqliteSkillSpecWriter"]
