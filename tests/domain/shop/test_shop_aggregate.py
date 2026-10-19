"""ShopAggregateのテスト"""
import pytest

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.entity.shop_listing import ShopListing
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.shop.exception.shop_exception import (
    ListingNotFoundException,
    NotShopOwnerException,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.value_object.shop_listing_projection import ShopListingProjection
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def _sample_listing_projection() -> ShopListingProjection:
    return ShopListingProjection(item_name="item", item_spec_id=1, quantity=1)


class TestShopAggregate:
    """ShopAggregateのテスト"""

    @pytest.fixture
    def shop_id(self) -> ShopId:
        return ShopId(1)

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId.create(1)

    @pytest.fixture
    def location_area_id(self) -> LocationAreaId:
        return LocationAreaId.create(1)

    @pytest.fixture
    def owner_id(self) -> PlayerId:
        return PlayerId(1)

    @pytest.fixture
    def other_player_id(self) -> PlayerId:
        return PlayerId(2)

    @pytest.fixture
    def shop(
        self,
        shop_id: ShopId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
        owner_id: PlayerId,
    ) -> ShopAggregate:
        """新規作成したショップ"""
        return ShopAggregate.create(
            shop_id=shop_id,
            spot_id=spot_id,
            location_area_id=location_area_id,
            owner_id=owner_id,
            name="テストショップ",
            description="説明",
        )

    class TestCreate:
        """createメソッドのテスト"""

        def test_create_success(
            self,
            shop_id: ShopId,
            spot_id: SpotId,
            location_area_id: LocationAreaId,
            owner_id: PlayerId,
        ):
            """ショップ作成が成功する"""
            shop = ShopAggregate.create(
                shop_id=shop_id,
                spot_id=spot_id,
                location_area_id=location_area_id,
                owner_id=owner_id,
                name="店",
                description="説明文",
            )
            assert shop.shop_id == shop_id
            assert shop.spot_id == spot_id
            assert shop.location_area_id == location_area_id
            assert shop.is_owner(owner_id) is True
            assert shop.name == "店"
            assert shop.description == "説明文"
            assert len(shop.listings) == 0

        def test_create_adds_shop_created_event(
            self,
            shop_id: ShopId,
            spot_id: SpotId,
            location_area_id: LocationAreaId,
            owner_id: PlayerId,
        ):
            """名前と説明を省略すると、既定値の空文字を含む開設イベントが1件発行される。"""
            shop = ShopAggregate.create(
                shop_id=shop_id,
                spot_id=spot_id,
                location_area_id=location_area_id,
                owner_id=owner_id,
            )
            events = shop.get_events()
            assert len(events) == 1
            assert isinstance(events[0], ShopCreatedEvent)
            assert events[0].aggregate_id == shop_id
            assert events[0].spot_id == spot_id
            assert events[0].location_area_id == location_area_id
            assert events[0].owner_id == owner_id
            assert events[0].name == ""
            assert events[0].description == ""
            assert events[0].owner_ids == (owner_id,)
            assert events[0].aggregate_type == "ShopAggregate"
            assert hasattr(events[0], "occurred_at")
            assert hasattr(events[0], "event_id")

    class TestIsOwner:
        """is_ownerメソッドのテスト"""

        def test_non_owner_returns_false(
            self, shop: ShopAggregate, other_player_id: PlayerId
        ):
            """オーナー以外はFalseを返す"""
            assert shop.is_owner(other_player_id) is False

    class TestListItem:
        """list_itemメソッドのテスト"""

        def test_list_item_success(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """オーナーの出品が保存され、その内容を含む出品イベントが1件発行される。"""
            shop.clear_events()
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            price = ShopListingPrice.of(50)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_id,
                price_per_unit=price,
                listed_by=owner_id,
                listing_projection=_sample_listing_projection(),
            )
            assert listing_id in shop.listings
            listing = shop.get_listing(listing_id)
            assert listing is not None
            assert listing.listing_id == listing_id
            assert listing.item_instance_id == item_id
            assert listing.price_per_unit == price
            assert listing.listed_by == owner_id
            events = shop.get_events()
            assert len(events) == 1
            assert isinstance(events[0], ShopItemListedEvent)

            event = events[0]
            assert event.aggregate_id == shop.shop_id
            assert event.aggregate_type == "ShopAggregate"
            assert event.listing_id == listing_id
            assert event.item_instance_id == item_id
            assert event.price_per_unit == price
            assert event.listed_by == owner_id
            assert event.listing_projection == _sample_listing_projection()
            assert hasattr(event, "occurred_at")
            assert hasattr(event, "event_id")

        @pytest.mark.parametrize("keep_pending_events", [False, True], ids=["empty_events", "pending_events"])
        def test_list_item_non_owner_raises(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
            other_player_id: PlayerId,
            keep_pending_events: bool,
        ):
            """非オーナーの出品は例外になり、既存の出品と未発行イベントを変更しない。"""
            shop.list_item(
                listing_id=ShopListingId(2),
                item_instance_id=ItemInstanceId(200),
                price_per_unit=ShopListingPrice.of(50),
                listed_by=owner_id,
                listing_projection=_sample_listing_projection(),
            )
            if not keep_pending_events:
                shop.clear_events()
            listings_before = shop.listings
            events_before = shop.get_events()
            assert bool(events_before) is keep_pending_events

            with pytest.raises(NotShopOwnerException):
                shop.list_item(
                    listing_id=ShopListingId(1),
                    item_instance_id=ItemInstanceId(100),
                    price_per_unit=ShopListingPrice.of(50),
                    listed_by=other_player_id,
                    listing_projection=_sample_listing_projection(),
                )

            assert shop.listings == listings_before
            assert shop.get_events() == events_before

    class TestUnlistItem:
        """unlist_itemメソッドのテスト"""

        def test_unlist_item_success(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """オーナーが取り下げると出品が消え、その情報を含む取り下げイベントが1件発行される。"""
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_id,
                price_per_unit=ShopListingPrice.of(50),
                listed_by=owner_id,
                listing_projection=_sample_listing_projection(),
            )
            shop.clear_events()
            shop.unlist_item(listing_id, owner_id)
            assert shop.get_listing(listing_id) is None
            events = shop.get_events()
            assert len(events) == 1
            assert isinstance(events[0], ShopItemUnlistedEvent)

            event = events[0]
            assert event.aggregate_id == shop.shop_id
            assert event.aggregate_type == "ShopAggregate"
            assert event.spot_id == shop.spot_id
            assert event.location_area_id == shop.location_area_id
            assert event.listing_id == listing_id
            assert event.unlisted_by == owner_id
            assert hasattr(event, "occurred_at")
            assert hasattr(event, "event_id")

        @pytest.mark.parametrize("keep_pending_events", [False, True], ids=["empty_events", "pending_events"])
        def test_unlist_item_non_owner_raises(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
            other_player_id: PlayerId,
            keep_pending_events: bool,
        ):
            """非オーナーの取り下げは例外になり、対象・他の出品・未発行イベントを変更しない。"""
            listing_id = ShopListingId(1)
            for existing_id, item_id in [(listing_id, ItemInstanceId(100)), (ShopListingId(2), ItemInstanceId(200))]:
                shop.list_item(
                    listing_id=existing_id,
                    item_instance_id=item_id,
                    price_per_unit=ShopListingPrice.of(50),
                    listed_by=owner_id,
                    listing_projection=_sample_listing_projection(),
                )
            if not keep_pending_events:
                shop.clear_events()
            listings_before = shop.listings
            events_before = shop.get_events()
            assert bool(events_before) is keep_pending_events

            with pytest.raises(NotShopOwnerException):
                shop.unlist_item(listing_id, other_player_id)

            assert shop.listings == listings_before
            assert shop.get_events() == events_before

        def test_unlist_nonexistent_listing_raises(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """存在しないリストを取り下げると例外"""
            with pytest.raises(ListingNotFoundException):
                shop.unlist_item(ShopListingId(999), owner_id)

    class TestRecordPurchase:
        """record_purchaseメソッドのテスト"""

        def test_record_purchase_adds_event_with_all_fields(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
            other_player_id: PlayerId,
        ):
            """購入を記録すると、出品・売買当事者・数量・総額を含む購入イベントが1件発行される。"""
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            price = ShopListingPrice.of(50)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_id,
                price_per_unit=price,
                listed_by=owner_id,
                listing_projection=_sample_listing_projection(),
            )
            shop.clear_events()
            shop.record_purchase(
                listing_id=listing_id,
                buyer_id=other_player_id,
                quantity=2,
                total_gold=100,
            )
            events = shop.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, ShopItemPurchasedEvent)
            assert event.aggregate_id == shop.shop_id
            assert event.aggregate_type == "ShopAggregate"
            assert event.listing_id == listing_id
            assert event.item_instance_id == item_id
            assert event.buyer_id == other_player_id
            assert event.quantity == 2
            assert event.total_gold == 100
            assert event.seller_id == owner_id
            assert hasattr(event, "occurred_at")
            assert hasattr(event, "event_id")

        def test_record_purchase_listing_not_found_raises(
            self,
            shop: ShopAggregate,
            other_player_id: PlayerId,
        ):
            """存在しないリストでrecord_purchaseすると例外"""
            with pytest.raises(ListingNotFoundException):
                shop.record_purchase(
                    listing_id=ShopListingId(999),
                    buyer_id=other_player_id,
                    quantity=1,
                    total_gold=50,
                )

    class TestRemoveListing:
        """remove_listingメソッドのテスト"""

        def test_remove_listing_success(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """リスト削除（在庫切れ用）が成功する"""
            listing_id = ShopListingId(1)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=ItemInstanceId(100),
                price_per_unit=ShopListingPrice.of(50),
                listed_by=owner_id,
                listing_projection=_sample_listing_projection(),
            )
            shop.remove_listing(listing_id)
            assert shop.get_listing(listing_id) is None

        def test_remove_listing_nonexistent_raises(self, shop: ShopAggregate):
            """存在しないリストを削除すると例外"""
            with pytest.raises(ListingNotFoundException):
                shop.remove_listing(ShopListingId(999))

    class TestGetListing:
        """get_listingメソッドのテスト"""

        def test_get_listing_nonexistent_returns_none(self, shop: ShopAggregate):
            """存在しないリストはNone"""
            assert shop.get_listing(ShopListingId(999)) is None

    class TestAddOwnerRemoveOwner:
        """add_owner / remove_ownerのテスト"""

        def test_add_owner_then_is_owner(
            self,
            shop: ShopAggregate,
            other_player_id: PlayerId,
        ):
            """オーナーを追加するとis_ownerがTrueになる"""
            assert shop.is_owner(other_player_id) is False
            shop.add_owner(other_player_id)
            assert shop.is_owner(other_player_id) is True

        def test_remove_owner_then_is_owner_false(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """オーナーを削除するとis_ownerがFalseになる"""
            shop.remove_owner(owner_id)
            assert shop.is_owner(owner_id) is False
