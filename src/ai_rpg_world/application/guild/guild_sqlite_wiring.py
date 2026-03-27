"""SQLite repository bundle for guild domain on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_guild_bank_repository import (
    SqliteGuildBankRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_guild_repository import (
    SqliteGuildRepository,
)


@dataclass(frozen=True)
class GuildSqliteRepositories:
    guilds: SqliteGuildRepository
    guild_banks: SqliteGuildBankRepository


def bootstrap_guild_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for guild state."""
    init_game_db_schema(connection)


def attach_guild_sqlite_repositories(
    connection: sqlite3.Connection,
) -> GuildSqliteRepositories:
    """Attach guild SQLite repositories to a shared connection."""
    return GuildSqliteRepositories(
        guilds=SqliteGuildRepository.for_shared_unit_of_work(connection),
        guild_banks=SqliteGuildBankRepository.for_shared_unit_of_work(connection),
    )


__all__ = [
    "GuildSqliteRepositories",
    "attach_guild_sqlite_repositories",
    "bootstrap_guild_schema",
]
