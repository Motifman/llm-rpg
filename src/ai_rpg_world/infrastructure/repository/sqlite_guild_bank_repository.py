"""SQLite implementation of guild bank aggregate repository."""

from __future__ import annotations

import sqlite3
from typing import List, Optional

from ai_rpg_world.domain.guild.aggregate.guild_bank_aggregate import GuildBankAggregate
from ai_rpg_world.domain.guild.repository.guild_bank_repository import GuildBankRepository
from ai_rpg_world.domain.guild.value_object.guild_id import GuildId
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.infrastructure.repository.game_write_sqlite_schema import (
    init_game_write_schema,
)


class SqliteGuildBankRepository(GuildBankRepository):
    def __init__(self, connection: sqlite3.Connection, *, _commits_after_write: bool) -> None:
        self._conn = connection
        self._commits_after_write = _commits_after_write
        if connection.row_factory is not sqlite3.Row:
            connection.row_factory = sqlite3.Row
        init_game_write_schema(connection)

    @classmethod
    def for_standalone_connection(cls, connection: sqlite3.Connection) -> "SqliteGuildBankRepository":
        return cls(connection, _commits_after_write=True)

    @classmethod
    def for_shared_unit_of_work(cls, connection: sqlite3.Connection) -> "SqliteGuildBankRepository":
        return cls(connection, _commits_after_write=False)

    def _finalize_write(self) -> None:
        if self._commits_after_write:
            self._conn.commit()

    def find_by_id(self, entity_id: GuildId) -> Optional[GuildBankAggregate]:
        cur = self._conn.execute(
            "SELECT guild_id, gold FROM game_guild_banks WHERE guild_id = ?",
            (int(entity_id),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return GuildBankAggregate(guild_id=GuildId(int(row["guild_id"])), gold=Gold.create(int(row["gold"])))

    def find_by_ids(self, entity_ids: List[GuildId]) -> List[GuildBankAggregate]:
        return [x for entity_id in entity_ids for x in [self.find_by_id(entity_id)] if x is not None]

    def find_all(self) -> List[GuildBankAggregate]:
        cur = self._conn.execute("SELECT guild_id, gold FROM game_guild_banks ORDER BY guild_id ASC")
        return [
            GuildBankAggregate(guild_id=GuildId(int(row["guild_id"])), gold=Gold.create(int(row["gold"])))
            for row in cur.fetchall()
        ]

    def save(self, entity: GuildBankAggregate) -> GuildBankAggregate:
        self._conn.execute(
            """
            INSERT INTO game_guild_banks (guild_id, gold)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                gold = excluded.gold
            """,
            (int(entity.guild_id), int(entity.gold.value)),
        )
        self._finalize_write()
        return entity

    def delete(self, entity_id: GuildId) -> bool:
        cur = self._conn.execute(
            "DELETE FROM game_guild_banks WHERE guild_id = ?",
            (int(entity_id),),
        )
        self._finalize_write()
        return cur.rowcount > 0


__all__ = ["SqliteGuildBankRepository"]
