"""SQLite repository bundle for shop domain on the single game DB."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ai_rpg_world.infrastructure.repository.game_db_schema import init_game_db_schema
from ai_rpg_world.infrastructure.repository.sqlite_shop_listing_read_model_repository import (
    SqliteShopListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_repository import (
    SqliteShopRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_summary_read_model_repository import (
    SqliteShopSummaryReadModelRepository,
)


@dataclass(frozen=True)
class ShopSqliteRepositories:
    shops: SqliteShopRepository
    shop_summaries: SqliteShopSummaryReadModelRepository
    shop_listings: SqliteShopListingReadModelRepository


def bootstrap_shop_schema(connection: sqlite3.Connection) -> None:
    """Initialize the single-file game DB schema for shop state and read models."""
    init_game_db_schema(connection)


def attach_shop_sqlite_repositories(
    connection: sqlite3.Connection,
) -> ShopSqliteRepositories:
    """Attach shop SQLite repositories to a shared connection."""
    return ShopSqliteRepositories(
        shops=SqliteShopRepository.for_shared_unit_of_work(connection),
        shop_summaries=SqliteShopSummaryReadModelRepository.for_shared_unit_of_work(
            connection
        ),
        shop_listings=SqliteShopListingReadModelRepository.for_shared_unit_of_work(
            connection
        ),
    )


__all__ = [
    "ShopSqliteRepositories",
    "attach_shop_sqlite_repositories",
    "bootstrap_shop_schema",
]
