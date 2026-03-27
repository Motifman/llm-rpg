"""SQLite implementation of loot table read repository and writer."""

from __future__ import annotations

import copy
import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate
from ai_rpg_world.domain.item.repository.loot_table_repository import (
    LootTableRepository,
    LootTableWriter,
)
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_loot_table_state_codec import (
    blob_to_loot_table,
    loot_table_to_blob,
)


class SqliteLootTableRepository(LootTableRepository):
    """Read loot tables from the game DB."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_connection(cls, connection: sqlite3.Connection) -> "SqliteLootTableRepository":
        return cls(connection)

    def find_by_id(self, entity_id: LootTableId) -> Optional[LootTableAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_loot_tables WHERE loot_table_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return copy.deepcopy(blob_to_loot_table(bytes(row["aggregate_blob"])))

    def find_all(self) -> List[LootTableAggregate]:
        cur = self._conn.execute(
            "SELECT aggregate_blob FROM game_loot_tables ORDER BY loot_table_id ASC"
        )
        return [
            copy.deepcopy(blob_to_loot_table(bytes(row["aggregate_blob"])))
            for row in cur.fetchall()
        ]

    def find_by_ids(self, entity_ids: List[LootTableId]) -> List[LootTableAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def save(self, entity: LootTableAggregate) -> LootTableAggregate:
        raise NotImplementedError(
            "SqliteLootTableRepository is read-only. Use SqliteLootTableWriter."
        )

    def delete(self, entity_id: LootTableId) -> bool:
        raise NotImplementedError(
            "SqliteLootTableRepository is read-only. Use SqliteLootTableWriter."
        )


class SqliteLootTableWriter(LootTableWriter):
    """LootTable 登録専用の SQLite writer。seed とテスト投入を担当する。"""

    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(
        cls, connection: sqlite3.Connection
    ) -> "SqliteLootTableWriter":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(
        cls, connection: sqlite3.Connection
    ) -> "SqliteLootTableWriter":
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

    def replace_table(self, table: LootTableAggregate) -> None:
        self._assert_shared_transaction_active()
        self._conn.execute(
            """
            INSERT INTO game_loot_tables (loot_table_id, name, aggregate_blob)
            VALUES (?, ?, ?)
            ON CONFLICT(loot_table_id) DO UPDATE SET
                name = excluded.name,
                aggregate_blob = excluded.aggregate_blob
            """,
            (
                int(table.loot_table_id),
                table.name,
                loot_table_to_blob(table),
            ),
        )
        self._finalize_write()

    def delete_table(self, loot_table_id: LootTableId) -> bool:
        self._assert_shared_transaction_active()
        cur = self._conn.execute(
            "DELETE FROM game_loot_tables WHERE loot_table_id = ?",
            (int(loot_table_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteLootTableRepository", "SqliteLootTableWriter"]
