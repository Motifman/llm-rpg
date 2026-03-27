"""SQLite shop repository tests."""

from __future__ import annotations

import sqlite3

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_shop_repository import (
    SqliteShopRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import SqliteUnitOfWork


def _shop(shop_id: int, spot_id: int = 10, location_area_id: int = 20) -> ShopAggregate:
    return ShopAggregate.create(
        shop_id=ShopId(shop_id),
        spot_id=SpotId(spot_id),
        location_area_id=LocationAreaId(location_area_id),
        owner_id=PlayerId(100),
        name="Test Shop",
        description="A test shop",
    )


def test_shop_repository_roundtrip_and_location_lookup() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteShopRepository.for_standalone_connection(conn)
    repo.save(_shop(1))

    loaded = repo.find_by_id(ShopId(1))
    assert loaded is not None
    assert loaded.shop_id == ShopId(1)
    assert loaded.name == "Test Shop"

    by_location = repo.find_by_spot_and_location(SpotId(10), LocationAreaId(20))
    assert by_location is not None
    assert by_location.shop_id == ShopId(1)


def test_shop_repository_generates_ids_inside_transaction() -> None:
    conn = sqlite3.connect(":memory:")
    uow = SqliteUnitOfWork(connection=conn)
    with uow:
        repo = SqliteShopRepository.for_shared_unit_of_work(uow.connection)
        assert repo.generate_shop_id() == ShopId(1)
        assert repo.generate_listing_id().value == 1
        assert repo.generate_shop_id() == ShopId(2)
