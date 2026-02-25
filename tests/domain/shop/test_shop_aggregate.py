"""ShopAggregateのテスト"""
import pytest
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.entity.shop_listing import ShopListing
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.shop.exception.shop_exception import (
    NotShopOwnerException,
    ListingNotFoundException,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


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
            """作成時にShopCreatedEventが発行される"""
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

    class TestIsOwner:
        """is_ownerメソッドのテスト"""

        def test_owner_returns_true(self, shop: ShopAggregate, owner_id: PlayerId):
            """オーナーはTrueを返す"""
            assert shop.is_owner(owner_id) is True

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
            """オーナーが出品すると成功する"""
            shop.clear_events()
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            price = ShopListingPrice.of(50)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_id,
                price_per_unit=price,
                listed_by=owner_id,
            )
            assert listing_id in shop.listings
            listing = shop.get_listing(listing_id)
            assert listing is not None
            assert listing.item_instance_id == item_id
            assert listing.price_per_unit == price
            assert listing.listed_by == owner_id
            events = shop.get_events()
            assert len(events) == 1
            assert isinstance(events[0], ShopItemListedEvent)

        def test_list_item_non_owner_raises(
            self,
            shop: ShopAggregate,
            other_player_id: PlayerId,
        ):
            """オーナー以外が出品すると例外"""
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            price = ShopListingPrice.of(50)
            with pytest.raises(NotShopOwnerException):
                shop.list_item(
                    listing_id=listing_id,
                    item_instance_id=item_id,
                    price_per_unit=price,
                    listed_by=other_player_id,
                )

    class TestUnlistItem:
        """unlist_itemメソッドのテスト"""

        def test_unlist_item_success(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """オーナーが取り下げると成功する"""
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_id,
                price_per_unit=ShopListingPrice.of(50),
                listed_by=owner_id,
            )
            shop.clear_events()
            shop.unlist_item(listing_id, owner_id)
            assert shop.get_listing(listing_id) is None
            events = shop.get_events()
            assert len(events) == 1
            assert isinstance(events[0], ShopItemUnlistedEvent)

        def test_unlist_item_non_owner_raises(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
            other_player_id: PlayerId,
        ):
            """オーナー以外が取り下げると例外"""
            listing_id = ShopListingId(1)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=ItemInstanceId(100),
                price_per_unit=ShopListingPrice.of(50),
                listed_by=owner_id,
            )
            with pytest.raises(NotShopOwnerException):
                shop.unlist_item(listing_id, other_player_id)

        def test_unlist_nonexistent_listing_raises(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """存在しないリストを取り下げると例外"""
            with pytest.raises(ListingNotFoundException):
                shop.unlist_item(ShopListingId(999), owner_id)

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
            )
            shop.remove_listing(listing_id)
            assert shop.get_listing(listing_id) is None

        def test_remove_listing_nonexistent_raises(self, shop: ShopAggregate):
            """存在しないリストを削除すると例外"""
            with pytest.raises(ListingNotFoundException):
                shop.remove_listing(ShopListingId(999))

    class TestGetListing:
        """get_listingメソッドのテスト"""

        def test_get_listing_returns_listing(
            self,
            shop: ShopAggregate,
            owner_id: PlayerId,
        ):
            """存在するリストを取得できる"""
            listing_id = ShopListingId(1)
            item_id = ItemInstanceId(100)
            shop.list_item(
                listing_id=listing_id,
                item_instance_id=item_id,
                price_per_unit=ShopListingPrice.of(50),
                listed_by=owner_id,
            )
            listing = shop.get_listing(listing_id)
            assert listing is not None
            assert listing.listing_id == listing_id
            assert listing.item_instance_id == item_id

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
