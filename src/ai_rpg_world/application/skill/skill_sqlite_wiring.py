"""SQLite repository bundle for skill domain on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_skill_deck_progress_repository import (
    SqliteSkillDeckProgressRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_loadout_repository import (
    SqliteSkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_skill_spec_repository import (
    SqliteSkillSpecRepository,
    SqliteSkillSpecWriter,
)


@dataclass(frozen=True)
class SkillRuntimeSqliteRepositories:
    loadouts: SqliteSkillLoadoutRepository
    deck_progresses: SqliteSkillDeckProgressRepository


@dataclass(frozen=True)
class SkillMasterSqliteRepositories:
    specs: SqliteSkillSpecRepository
    spec_writer: SqliteSkillSpecWriter


@dataclass(frozen=True)
class SkillSqliteRepositories:
    runtime: SkillRuntimeSqliteRepositories
    master: SkillMasterSqliteRepositories


def bootstrap_skill_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for skill state."""
    init_game_db_schema(connection)


def attach_skill_sqlite_repositories(
    connection: sqlite3.Connection,
) -> SkillSqliteRepositories:
    """Attach skill SQLite repositories to a shared connection."""
    return SkillSqliteRepositories(
        runtime=SkillRuntimeSqliteRepositories(
            loadouts=SqliteSkillLoadoutRepository.for_shared_unit_of_work(connection),
            deck_progresses=SqliteSkillDeckProgressRepository.for_shared_unit_of_work(
                connection
            ),
        ),
        master=SkillMasterSqliteRepositories(
            specs=SqliteSkillSpecRepository.for_connection(connection),
            spec_writer=SqliteSkillSpecWriter.for_shared_unit_of_work(connection),
        ),
    )


__all__ = [
    "SkillRuntimeSqliteRepositories",
    "SkillMasterSqliteRepositories",
    "SkillSqliteRepositories",
    "attach_skill_sqlite_repositories",
    "bootstrap_skill_schema",
]
