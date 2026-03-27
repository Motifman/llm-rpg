"""SQLite implementation of spawn table read repository and writer."""

from __future__ import annotations

import copy
import sqlite3
from typing import Optional

from ai_rpg_world.domain.monster.repository.spawn_table_repository import (
    SpawnTableRepository,
    SpawnTableWriter,
)
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_spawn_table_state_codec import (
    blob_to_spawn_table,
    spawn_table_to_blob,
)


class SqliteSpawnTableRepository(SpawnTableRepository):
    """Read spot-based spawn tables from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteSpawnTableRepository":
        return cls(connection)

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotSpawnTable]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_spawn_tables WHERE spot_id = ?",
            (int(spot_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_spawn_table(bytes(row["aggregate_blob"])))


class SqliteSpawnTableWriter(SpawnTableWriter):
    """SpawnTable 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteSpawnTableWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteSpawnTableWriter":
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

    def replace_table(self, table: SpotSpawnTable) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_spawn_tables (spot_id, aggregate_blob)
            VALUES (?, ?)
            ON CONFLICT(spot_id) DO UPDATE SET aggregate_blob = excluded.aggregate_blob
            """,
            (int(table.spot_id), spawn_table_to_blob(table)),
        )
        self._finalize_write()


__all__ = ["SqliteSpawnTableRepository", "SqliteSpawnTableWriter"]
