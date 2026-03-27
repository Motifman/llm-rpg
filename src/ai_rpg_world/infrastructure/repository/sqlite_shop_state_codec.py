"""Shop aggregate and read model helpers for SQLite repositories."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.entity.shop_listing import ShopListing
from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def build_shop(*, row: object, owner_rows: list[object], listing_rows: list[object]) -> ShopAggregate:
    listings = {
        ShopListingId(int(listing_row["listing_id"])): ShopListing(
            listing_id=ShopListingId(int(listing_row["listing_id"])),
            item_instance_id=ItemInstanceId(int(listing_row["item_instance_id"])),
            price_per_unit=ShopListingPrice.of(int(listing_row["price_per_unit"])),
            listed_by=PlayerId(int(listing_row["listed_by"])),
        )
        for listing_row in listing_rows
    }
    return ShopAggregate(
        shop_id=ShopId(int(row["shop_id"])),
        spot_id=SpotId(int(row["spot_id"])),
        location_area_id=LocationAreaId(int(row["location_area_id"])),
        owner_ids={PlayerId(int(owner_row["owner_id"])) for owner_row in owner_rows},
        name=str(row["name"]),
        description=str(row["description"]),
        listings=listings,
    )


def shop_summary_row_to_model(row: Any) -> ShopSummaryReadModel:
    owner_ids = json.loads(str(row["owner_ids_json"]))
    created_at = datetime.fromisoformat(str(row["created_at"]))
    return ShopSummaryReadModel(
        shop_id=int(row["shop_id"]),
        spot_id=int(row["spot_id"]),
        location_area_id=int(row["location_area_id"]),
        name=str(row["name"]),
        description=str(row["description"]),
        owner_ids=[int(owner_id) for owner_id in owner_ids],
        listing_count=int(row["listing_count"]),
        created_at=created_at,
    )


def shop_listing_row_to_model(row: Any) -> ShopListingReadModel:
    listed_at_raw = row["listed_at"]
    listed_at = None if listed_at_raw is None else datetime.fromisoformat(str(listed_at_raw))
    return ShopListingReadModel(
        shop_id=int(row["shop_id"]),
        listing_id=int(row["listing_id"]),
        item_instance_id=int(row["item_instance_id"]),
        item_name=str(row["item_name"]),
        item_spec_id=int(row["item_spec_id"]),
        price_per_unit=int(row["price_per_unit"]),
        quantity=int(row["quantity"]),
        listed_by=int(row["listed_by"]),
        listed_at=listed_at,
    )


__all__ = ["build_shop", "shop_summary_row_to_model", "shop_listing_row_to_model"]
