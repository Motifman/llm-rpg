"""SQLite repository bundle for world/player state on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_hit_box_repository import (
    SqliteHitBoxRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_item_write_repository import SqliteItemWriteRepository
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


@dataclass(frozen=True)
class PlayerStateSqliteRepositories:
    player_profiles: SqlitePlayerProfileWriteRepository
    player_statuses: SqlitePlayerStatusWriteRepository
    player_inventories: SqlitePlayerInventoryWriteRepository
    items: SqliteItemWriteRepository


@dataclass(frozen=True)
class WorldRuntimeSqliteRepositories:
    physical_maps: SqlitePhysicalMapRepository
    monsters: SqliteMonsterAggregateRepository
    hit_boxes: SqliteHitBoxRepository


@dataclass(frozen=True)
class WorldStructureSqliteRepositories:
    spots: SqliteSpotRepository
    location_establishments: SqliteLocationEstablishmentRepository


@dataclass(frozen=True)
class WorldStateSqliteRepositories:
    player_state: PlayerStateSqliteRepositories
    world_runtime: WorldRuntimeSqliteRepositories
    world_structure: WorldStructureSqliteRepositories


def bootstrap_world_state_schema(connection: sqlite3.Connection) -> None:
    """Initialize the current single-file game DB schema for world/player state."""
    init_game_db_schema(connection)


def attach_world_state_sqlite_repositories(
    connection: sqlite3.Connection,
    *,
    event_sink: Any = None,
) -> WorldStateSqliteRepositories:
    """Attach world/player SQLite repositories to a shared UoW connection."""
    return WorldStateSqliteRepositories(
        player_state=PlayerStateSqliteRepositories(
            player_profiles=SqlitePlayerProfileWriteRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
            player_statuses=SqlitePlayerStatusWriteRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
            player_inventories=SqlitePlayerInventoryWriteRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
            items=SqliteItemWriteRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
        ),
        world_runtime=WorldRuntimeSqliteRepositories(
            physical_maps=SqlitePhysicalMapRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
            monsters=SqliteMonsterAggregateRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
            hit_boxes=SqliteHitBoxRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
        ),
        world_structure=WorldStructureSqliteRepositories(
            spots=SqliteSpotRepository.for_shared_unit_of_work(connection),
            location_establishments=SqliteLocationEstablishmentRepository.for_shared_unit_of_work(
                connection, event_sink=event_sink
            ),
        ),
    )


__all__ = [
    "PlayerStateSqliteRepositories",
    "WorldRuntimeSqliteRepositories",
    "WorldStructureSqliteRepositories",
    "WorldStateSqliteRepositories",
    "attach_world_state_sqlite_repositories",
    "bootstrap_world_state_schema",
]
