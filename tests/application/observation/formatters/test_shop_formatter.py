"""ShopObservationFormatter の単体テスト。"""

from unittest.mock import MagicMock

from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.application.observation.services.formatters.name_resolver import (
    ObservationNameResolver,
)
from ai_rpg_world.application.observation.services.formatters.shop_formatter import (
    ShopObservationFormatter,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import ShopItemListedEvent, ShopItemPurchasedEvent
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.value_object.shop_listing_projection import ShopListingProjection
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def _listing_projection() -> ShopListingProjection:
    return ShopListingProjection(item_name="薬草", item_spec_id=1, quantity=1)


def _make_context(item_repository=None) -> ObservationFormatterContext:
    name_resolver = ObservationNameResolver(
        spot_repository=None,
        player_profile_repository=None,
        item_spec_repository=None,
        item_repository=item_repository,
        shop_repository=None,
        guild_repository=None,
        monster_repository=None,
        skill_spec_repository=None,
        sns_user_repository=None,
    )
    return ObservationFormatterContext(
        name_resolver=name_resolver,
        item_repository=item_repository,
    )


class TestShopObservationFormatterItemListed:
    """ShopItemListedEvent の structured に item_spec_id_value が載ること。"""

    def test_includes_item_spec_id_value_when_repository_resolves(self) -> None:
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.item_spec_id.value = 440
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = ShopObservationFormatter(ctx)
        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(7),
            location_area_id=LocationAreaId(1),
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(99),
            price_per_unit=ShopListingPrice.of(50),
            listed_by=PlayerId(1),
            listing_projection=_listing_projection(),
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert out.structured.get("type") == "shop_item_listed"
        assert out.structured.get("item_spec_id_value") == 440


class TestShopObservationFormatterItemPurchased:
    """ShopItemPurchasedEvent の structured に item_spec_id_value が載ること。"""

    def test_buyer_observation_includes_item_spec_id_value(self) -> None:
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.item_spec_id.value = 551
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = ShopObservationFormatter(ctx)
        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(11),
            buyer_id=PlayerId(2),
            quantity=2,
            total_gold=40,
            seller_id=PlayerId(7),
        )
        out = formatter.format(event, PlayerId(2))
        assert out is not None
        assert out.structured.get("type") == "shop_purchase"
        assert out.structured.get("role") == "buyer"
        assert out.structured.get("item_spec_id_value") == 551

    def test_seller_observation_includes_item_spec_id_value(self) -> None:
        item_repo = MagicMock()
        agg = MagicMock()
        agg.item_spec.item_spec_id.value = 552
        item_repo.find_by_id.return_value = agg
        ctx = _make_context(item_repository=item_repo)
        formatter = ShopObservationFormatter(ctx)
        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(1),
            item_instance_id=ItemInstanceId(11),
            buyer_id=PlayerId(2),
            quantity=2,
            total_gold=40,
            seller_id=PlayerId(7),
        )
        out = formatter.format(event, PlayerId(7))
        assert out is not None
        assert out.structured.get("role") == "seller"
        assert out.structured.get("item_spec_id_value") == 552
