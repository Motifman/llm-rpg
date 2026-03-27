"""shop_sqlite_wiring tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.application.shop.shop_sqlite_wiring import (
    ShopSqliteRepositories,
    attach_shop_sqlite_repositories,
    bootstrap_shop_schema,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_listing_read_model_repository import (
    SqliteShopListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_repository import (
    SqliteShopRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_summary_read_model_repository import (
    SqliteShopSummaryReadModelRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def test_bootstrap_materializes_shop_tables() -> None:
    conn = sqlite3.connect(":memory:")
    bootstrap_shop_schema(conn)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    names = {row[0] for row in cur.fetchall()}
    assert "game_shops" in names
    assert "game_shop_summary_read_models" in names
    assert "game_shop_listing_read_models" in names


def test_attach_returns_shared_shop_repositories() -> None:
    conn = sqlite3.connect(":memory:")
    uow = SqliteUnitOfWork(connection=conn)
    with uow:
        bundle = attach_shop_sqlite_repositories(uow.connection)

    assert isinstance(bundle, ShopSqliteRepositories)
    assert isinstance(bundle.shops, SqliteShopRepository)
    assert isinstance(bundle.shop_summaries, SqliteShopSummaryReadModelRepository)
    assert isinstance(bundle.shop_listings, SqliteShopListingReadModelRepository)
