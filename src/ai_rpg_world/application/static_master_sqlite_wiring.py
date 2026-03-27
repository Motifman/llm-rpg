"""SQLite repository bundle for static master data on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_item_spec_repository import (
    SqliteItemSpecRepository,
    SqliteItemSpecWriter,
)
from ai_rpg_world.infrastructure.repository.sqlite_loot_table_repository import (
    SqliteLootTableRepository,
    SqliteLootTableWriter,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_template_repository import (
    SqliteMonsterTemplateRepository,
    SqliteMonsterTemplateWriter,
)
from ai_rpg_world.infrastructure.repository.sqlite_recipe_repository import (
    SqliteRecipeRepository,
    SqliteRecipeWriter,
)
from ai_rpg_world.infrastructure.repository.sqlite_spawn_table_repository import (
    SqliteSpawnTableRepository,
    SqliteSpawnTableWriter,
)


@dataclass(frozen=True)
class StaticMasterReadSqliteRepositories:
    spawn_tables: SqliteSpawnTableRepository
    monster_templates: SqliteMonsterTemplateRepository
    loot_tables: SqliteLootTableRepository
    item_specs: SqliteItemSpecRepository
    recipes: SqliteRecipeRepository


@dataclass(frozen=True)
class StaticMasterWriteSqliteRepositories:
    spawn_tables: SqliteSpawnTableWriter
    monster_templates: SqliteMonsterTemplateWriter
    loot_tables: SqliteLootTableWriter
    item_specs: SqliteItemSpecWriter
    recipes: SqliteRecipeWriter


@dataclass(frozen=True)
class StaticMasterSqliteRepositories:
    readers: StaticMasterReadSqliteRepositories
    writers: StaticMasterWriteSqliteRepositories


def bootstrap_static_master_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for static master data."""
    init_game_db_schema(connection)


def attach_static_master_sqlite_repositories(
    connection: sqlite3.Connection,
) -> StaticMasterSqliteRepositories:
    """Attach static master SQLite repositories to a shared connection."""
    return StaticMasterSqliteRepositories(
        readers=StaticMasterReadSqliteRepositories(
            spawn_tables=SqliteSpawnTableRepository.for_connection(connection),
            monster_templates=SqliteMonsterTemplateRepository.for_connection(connection),
            loot_tables=SqliteLootTableRepository.for_connection(connection),
            item_specs=SqliteItemSpecRepository.for_connection(connection),
            recipes=SqliteRecipeRepository.for_connection(connection),
        ),
        writers=StaticMasterWriteSqliteRepositories(
            spawn_tables=SqliteSpawnTableWriter.for_shared_unit_of_work(connection),
            monster_templates=SqliteMonsterTemplateWriter.for_shared_unit_of_work(
                connection
            ),
            loot_tables=SqliteLootTableWriter.for_shared_unit_of_work(connection),
            item_specs=SqliteItemSpecWriter.for_shared_unit_of_work(connection),
            recipes=SqliteRecipeWriter.for_shared_unit_of_work(connection),
        ),
    )


__all__ = [
    "StaticMasterReadSqliteRepositories",
    "StaticMasterWriteSqliteRepositories",
    "StaticMasterSqliteRepositories",
    "attach_static_master_sqlite_repositories",
    "bootstrap_static_master_schema",
]
