"""SQLite shop read model repository tests."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_shop_listing_read_model_repository import (
    SqliteShopListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_summary_read_model_repository import (
    SqliteShopSummaryReadModelRepository,
)


def test_shop_summary_read_model_repository_filters_by_location_and_spot() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteShopSummaryReadModelRepository.for_standalone_connection(conn)
    repo.save(
        ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Shop 1",
            description="Desc",
            owner_ids=[PlayerId(100)],
            listing_count=1,
            created_at=datetime.now(),
        )
    )

    by_location = repo.find_by_spot_and_location(SpotId(10), LocationAreaId(20))
    by_spot = repo.find_all_by_spot_id(SpotId(10))
    assert by_location is not None
    assert by_location.shop_id == 1
    assert [item.shop_id for item in by_spot] == [1]


def test_shop_listing_read_model_repository_filters_by_shop() -> None:
    conn = sqlite3.connect(":memory:")
    repo = SqliteShopListingReadModelRepository.for_standalone_connection(conn)
    repo.save(
        ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(201),
            item_name="Potion",
            item_spec_id=7,
            price_per_unit=50,
            quantity=3,
            listed_by=PlayerId(100),
        )
    )

    loaded = repo.find_by_id(ShopListingId(101))
    by_shop = repo.find_by_shop_id(ShopId(1))
    assert loaded is not None
    assert loaded.item_name == "Potion"
    assert [item.listing_id for item in by_shop] == [101]
