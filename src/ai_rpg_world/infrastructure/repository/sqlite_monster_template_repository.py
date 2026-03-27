"""SQLite implementation of monster template read repository and writer."""

from __future__ import annotations

import copy
import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.monster.repository.monster_repository import (
    MonsterTemplateRepository,
    MonsterTemplateWriter,
)
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_template_state_codec import (
    blob_to_monster_template,
    monster_template_to_blob,
)


class SqliteMonsterTemplateRepository(MonsterTemplateRepository):
    """Read monster templates from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteMonsterTemplateRepository":
        return cls(connection)

    def find_by_id(
        self, template_id: MonsterTemplateId
    ) -> Optional[MonsterTemplate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monster_templates WHERE template_id = ?",
            (int(template_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_monster_template(bytes(row["aggregate_blob"])))

    def find_by_ids(
        self, template_ids: List[MonsterTemplateId]
    ) -> List[MonsterTemplate]:
        return [x for template_id in template_ids for x in [self.find_by_id(template_id)] if x is not None]

    def find_by_name(self, name: str) -> Optional[MonsterTemplate]:
        if not name or not isinstance(name, str):
            return None
        key = name.strip()
        if not key:
            return None

        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monster_templates WHERE name = ?",
            (key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_monster_template(bytes(row["aggregate_blob"])))

    def save(self, template: MonsterTemplate) -> MonsterTemplate:
        raise NotImplementedError(
            "SqliteMonsterTemplateRepository is read-only. Use SqliteMonsterTemplateWriter."
        )

    def delete(self, template_id: MonsterTemplateId) -> bool:
        raise NotImplementedError(
            "SqliteMonsterTemplateRepository is read-only. Use SqliteMonsterTemplateWriter."
        )

    def find_all(self) -> List[MonsterTemplate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_monster_templates ORDER BY template_id ASC"
        )
        return [
            copy.deepcopy(blob_to_monster_template(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]


class SqliteMonsterTemplateWriter(MonsterTemplateWriter):
    """MonsterTemplate 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteMonsterTemplateWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteMonsterTemplateWriter":
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

    def replace_template(self, template: MonsterTemplate) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_monster_templates (template_id, name, aggregate_blob)
            VALUES (?, ?, ?)
            ON CONFLICT(template_id) DO UPDATE SET
                name = excluded.name,
                aggregate_blob = excluded.aggregate_blob
            """,
            (
                int(template.template_id),
                template.name,
                monster_template_to_blob(template),
            ),
        )
        self._finalize_write()

    def delete_template(self, template_id: MonsterTemplateId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_monster_templates WHERE template_id = ?",
            (int(template_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteMonsterTemplateRepository", "SqliteMonsterTemplateWriter"]
