"""SQLite repository bundle for conversation domain on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_dialogue_tree_repository import (
    SqliteDialogueTreeRepository,
    SqliteDialogueTreeWriter,
)


@dataclass(frozen=True)
class ConversationSqliteRepositories:
    dialogue_trees: SqliteDialogueTreeRepository
    dialogue_tree_writer: SqliteDialogueTreeWriter


def bootstrap_conversation_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for conversation state."""
    init_game_db_schema(connection)


def attach_conversation_sqlite_repositories(
    connection: sqlite3.Connection,
) -> ConversationSqliteRepositories:
    """Attach conversation SQLite repositories to a shared connection."""
    return ConversationSqliteRepositories(
        dialogue_trees=SqliteDialogueTreeRepository.for_connection(connection),
        dialogue_tree_writer=SqliteDialogueTreeWriter.for_shared_unit_of_work(connection),
    )


__all__ = [
    "ConversationSqliteRepositories",
    "attach_conversation_sqlite_repositories",
    "bootstrap_conversation_schema",
]
