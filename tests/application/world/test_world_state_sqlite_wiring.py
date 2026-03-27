"""world_state_sqlite_wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.world.world_state_sqlite_wiring import (
    PlayerStateSqliteRepositories,
    WorldRuntimeSqliteRepositories,
    WorldStructureSqliteRepositories,
    WorldStateSqliteRepositories,
    attach_world_state_sqlite_repositories,
    bootstrap_world_state_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_hit_box_repository import (
    SqliteHitBoxRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import (
    SqliteItemWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_location_establishment_repository import (
    SqliteLocationEstablishmentRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_monster_aggregate_repository import (
    SqliteMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_physical_map_repository import (
    SqlitePhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_inventory_write_repository import (
    SqlitePlayerInventoryWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_profile_write_repository import (
    SqlitePlayerProfileWriteRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_spot_repository import (
    SqliteSpotRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_player_status_write_repository import (
    SqlitePlayerStatusWriteRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


class TestWorldStateSqliteWiring:
    def test_bootstrap_materializes_world_state_tables(self) -> None:
        conn = sqlite3.connect(":memory:")
        bootstrap_world_state_schema(conn)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        names = {row[0] for row in cur.fetchall()}
        assert "game_physical_maps" in names
        assert "game_world_object_locations" in names
        assert "game_monsters" in names
        assert "game_hit_boxes" in names
        assert "game_spots" in names
        assert "game_location_establishments" in names

    def test_attach_returns_shared_repositories(self) -> None:
        conn = sqlite3.connect(":memory:")
        uow = SqliteUnitOfWork(connection=conn)
        with uow:
            bundle = attach_world_state_sqlite_repositories(uow.connection, event_sink=uow)

        assert isinstance(bundle, WorldStateSqliteRepositories)
        assert isinstance(bundle.player_state, PlayerStateSqliteRepositories)
        assert isinstance(bundle.world_runtime, WorldRuntimeSqliteRepositories)
        assert isinstance(bundle.world_structure, WorldStructureSqliteRepositories)
        assert isinstance(bundle.player_state.player_profiles, SqlitePlayerProfileWriteRepository)
        assert isinstance(bundle.player_state.player_statuses, SqlitePlayerStatusWriteRepository)
        assert isinstance(bundle.player_state.player_inventories, SqlitePlayerInventoryWriteRepository)
        assert isinstance(bundle.player_state.items, SqliteItemWriteRepository)
        assert isinstance(bundle.world_runtime.physical_maps, SqlitePhysicalMapRepository)
        assert isinstance(bundle.world_runtime.monsters, SqliteMonsterAggregateRepository)
        assert isinstance(bundle.world_runtime.hit_boxes, SqliteHitBoxRepository)
        assert isinstance(bundle.world_structure.spots, SqliteSpotRepository)
        assert isinstance(
            bundle.world_structure.location_establishments,
            SqliteLocationEstablishmentRepository,
        )
