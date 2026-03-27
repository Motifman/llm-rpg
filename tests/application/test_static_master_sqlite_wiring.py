"""static_master_sqlite_wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.static_master_sqlite_wiring import (
    StaticMasterReadSqliteRepositories,
    StaticMasterSqliteRepositories,
    StaticMasterWriteSqliteRepositories,
    attach_static_master_sqlite_repositories,
    bootstrap_static_master_schema,
)
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
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class TestStaticMasterSqliteWiring:
    def test_bootstrap_materializes_static_master_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        bootstrap_static_master_schema(conn)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row[0] for row in cur.fetchall()}
        assert "game_spawn_tables" in names
        assert "game_monster_templates" in names
        assert "game_loot_tables" in names
        assert "game_item_specs" in names
        assert "game_recipes" in names
        assert "game_recipe_ingredients" in names

    def test_attach_returns_reader_and_writer_bundles(self) -> None:
        conn = sqlite3.connect(":memory:")
        uow = SqliteUnitOfWork(connection=conn)
        with uow:
            bundle = attach_static_master_sqlite_repositories(uow.connection)

        assert isinstance(bundle, StaticMasterSqliteRepositories)
        assert isinstance(bundle.readers, StaticMasterReadSqliteRepositories)
        assert isinstance(bundle.writers, StaticMasterWriteSqliteRepositories)
        assert isinstance(bundle.readers.spawn_tables, SqliteSpawnTableRepository)
        assert isinstance(bundle.readers.monster_templates, SqliteMonsterTemplateRepository)
        assert isinstance(bundle.readers.loot_tables, SqliteLootTableRepository)
        assert isinstance(bundle.readers.item_specs, SqliteItemSpecRepository)
        assert isinstance(bundle.readers.recipes, SqliteRecipeRepository)
        assert isinstance(bundle.writers.spawn_tables, SqliteSpawnTableWriter)
        assert isinstance(bundle.writers.monster_templates, SqliteMonsterTemplateWriter)
        assert isinstance(bundle.writers.loot_tables, SqliteLootTableWriter)
        assert isinstance(bundle.writers.item_specs, SqliteItemSpecWriter)
        assert isinstance(bundle.writers.recipes, SqliteRecipeWriter)
