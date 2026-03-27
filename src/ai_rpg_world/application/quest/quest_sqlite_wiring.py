"""SQLite repository bundle for quest domain on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_quest_repository import (
    SqliteQuestRepository,
)


@dataclass(frozen=True)
class QuestSqliteRepositories:
    quests: SqliteQuestRepository


def bootstrap_quest_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for quest state."""
    init_game_db_schema(connection)


def attach_quest_sqlite_repositories(
    connection: sqlite3.Connection,
) -> QuestSqliteRepositories:
    """Attach quest SQLite repositories to a shared connection."""
    return QuestSqliteRepositories(
        quests=SqliteQuestRepository.for_shared_unit_of_work(connection),
    )


__all__ = [
    "QuestSqliteRepositories",
    "attach_quest_sqlite_repositories",
    "bootstrap_quest_schema",
]
