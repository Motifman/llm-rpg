"""SQLite integration tests for shop query and event handler flows."""

from __future__ import annotations

from datetime import datetime

import sqlite3

from ai_rpg_world.application.shop.handlers.shop_event_handler import ShopEventHandler
from ai_rpg_world.application.shop.services.shop_query_service import ShopQueryService
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import ShopCreatedEvent, ShopItemListedEvent
from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.value_object.shop_listing_projection import ShopListingProjection
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.sqlite_shop_listing_read_model_repository import (
    SqliteShopListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.sqlite_shop_summary_read_model_repository import (
    SqliteShopSummaryReadModelRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.sqlite_unit_of_work import (
    SqliteUnitOfWorkFactory,
)


def test_shop_query_service_reads_sqlite_read_models(tmp_path) -> None:
    db_path = tmp_path / "shop-query.sqlite3"
    summary_repo = SqliteShopSummaryReadModelRepository.for_standalone_connection(
        sqlite3.connect(db_path)
    )
    listing_repo = SqliteShopListingReadModelRepository.for_standalone_connection(
        sqlite3.connect(db_path)
    )
    summary_repo.save(
        ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="SQLite Shop",
            description="Desc",
            owner_ids=[PlayerId(100)],
            listing_count=1,
            created_at=datetime.now(),
        )
    )
    listing_repo.save(
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

    service = ShopQueryService(summary_repo, listing_repo)
    detail = service.get_shop_detail(1)
    assert detail.summary.name == "SQLite Shop"
    assert detail.listings[0].item_name == "Potion"


def test_shop_event_handler_updates_sqlite_read_models(tmp_path) -> None:
    db_path = tmp_path / "shop-event.sqlite3"

    summary_conn = sqlite3.connect(db_path)
    listing_conn = sqlite3.connect(db_path)
    summary_repo = SqliteShopSummaryReadModelRepository.for_standalone_connection(summary_conn)
    listing_repo = SqliteShopListingReadModelRepository.for_standalone_connection(listing_conn)
    handler = ShopEventHandler(
        shop_summary_read_model_repository=summary_repo,
        shop_listing_read_model_repository=listing_repo,
        unit_of_work_factory=SqliteUnitOfWorkFactory(db_path),
    )

    created = ShopCreatedEvent.create(
        aggregate_id=ShopId(1),
        aggregate_type="ShopAggregate",
        spot_id=SpotId(10),
        location_area_id=LocationAreaId(20),
        owner_id=PlayerId(100),
        name="SQLite Shop",
        description="Desc",
        owner_ids=(PlayerId(100),),
    )
    handler.handle_shop_created(created)

    listed = ShopItemListedEvent.create(
        aggregate_id=ShopId(1),
        aggregate_type="ShopAggregate",
        spot_id=SpotId(10),
        location_area_id=LocationAreaId(20),
        listing_id=ShopListingId(101),
        item_instance_id=ItemInstanceId(201),
        price_per_unit=ShopListingPrice.of(50),
        listed_by=PlayerId(100),
        listing_projection=ShopListingProjection(
            item_name="Potion",
            item_spec_id=7,
            quantity=3,
        ),
    )
    handler.handle_shop_item_listed(listed)

    assert summary_repo.find_by_id(ShopId(1)) is not None
    assert summary_repo.find_by_id(ShopId(1)).listing_count == 1
    assert listing_repo.find_by_id(ShopListingId(101)) is not None
