"""ShopEventHandlerのテスト"""
import pytest
from datetime import datetime
from unittest.mock import Mock

from ai_rpg_world.application.shop.handlers.shop_event_handler import ShopEventHandler
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemUnlistedEvent,
    ShopItemPurchasedEvent,
)
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId

from ai_rpg_world.infrastructure.repository.in_memory_shop_summary_read_model_repository import (
    InMemoryShopSummaryReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_shop_listing_read_model_repository import (
    InMemoryShopListingReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_shop_repository import (
    InMemoryShopRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class TestShopEventHandler:
    """ShopEventHandlerのテストクラス"""

    @pytest.fixture
    def setup_handler(self):
        """ハンドラとリポジトリをセットアップ"""
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow)

        data_store = InMemoryDataStore()
        summary_repo = InMemoryShopSummaryReadModelRepository()
        listing_repo = InMemoryShopListingReadModelRepository()
        shop_repo = InMemoryShopRepository(data_store=data_store)
        item_repo = Mock()

        uow_factory = Mock()
        uow_factory.create.side_effect = create_uow

        handler = ShopEventHandler(
            shop_summary_read_model_repository=summary_repo,
            shop_listing_read_model_repository=listing_repo,
            shop_repository=shop_repo,
            item_repository=item_repo,
            unit_of_work_factory=uow_factory,
        )
        return handler, summary_repo, listing_repo, shop_repo, item_repo

    def test_handle_shop_created(self, setup_handler):
        """ショップ開設イベントでサマリReadModelが作成される"""
        handler, summary_repo, listing_repo, shop_repo, _ = setup_handler

        shop = ShopAggregate.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            owner_id=PlayerId(100),
            name="Test Shop",
            description="A test shop",
        )
        shop_repo.save(shop)

        event = ShopCreatedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            owner_id=PlayerId(100),
        )

        handler.handle_shop_created(event)

        summary = summary_repo.find_by_id(ShopId(1))
        assert summary is not None
        assert summary.shop_id == 1
        assert summary.spot_id == 10
        assert summary.location_area_id == 20
        assert summary.name == "Test Shop"
        assert summary.description == "A test shop"
        assert summary.owner_ids == [100]
        assert summary.listing_count == 0

    def test_handle_shop_created_shop_not_found_does_not_raise(self, setup_handler):
        """集約が存在しない場合はログのみで例外にしない"""
        handler, summary_repo, _, shop_repo, _ = setup_handler
        # shop_repo には何も保存しない

        event = ShopCreatedEvent.create(
            aggregate_id=ShopId(999),
            aggregate_type="ShopAggregate",
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            owner_id=PlayerId(100),
        )

        handler.handle_shop_created(event)

        assert summary_repo.find_by_id(ShopId(999)) is None

    def test_handle_shop_item_listed(self, setup_handler):
        """出品イベントでリストReadModelが追加され、サマリのlisting_countが増える"""
        handler, summary_repo, listing_repo, shop_repo, item_repo = setup_handler

        shop = ShopAggregate.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            owner_id=PlayerId(100),
            name="Shop",
            description="",
        )
        shop_repo.save(shop)

        from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import (
            ShopSummaryReadModel,
        )

        summary_rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Shop",
            description="",
            owner_ids=[PlayerId(100)],
            listing_count=0,
            created_at=datetime.now(),
        )
        summary_repo.save(summary_rm)

        mock_item = Mock()
        mock_item.item_spec.name = "Test Sword"
        mock_item.item_spec.item_spec_id = ItemSpecId(5)
        mock_item.item_instance.quantity = 3
        item_repo.find_by_id.return_value = mock_item

        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            price_per_unit=ShopListingPrice.of(50),
            listed_by=PlayerId(100),
        )

        handler.handle_shop_item_listed(event)

        listing = listing_repo.find_by_id(ShopListingId(101))
        assert listing is not None
        assert listing.shop_id == 1
        assert listing.listing_id == 101
        assert listing.item_name == "Test Sword"
        assert listing.quantity == 3
        assert listing.price_per_unit == 50

        summary = summary_repo.find_by_id(ShopId(1))
        assert summary is not None
        assert summary.listing_count == 1

    def test_handle_shop_item_listed_item_not_found_does_not_raise(self, setup_handler):
        """アイテムが存在しない場合はログのみで例外にしない"""
        handler, summary_repo, listing_repo, shop_repo, item_repo = setup_handler
        shop = ShopAggregate.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            owner_id=PlayerId(100),
        )
        shop_repo.save(shop)
        item_repo.find_by_id.return_value = None

        event = ShopItemListedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            price_per_unit=ShopListingPrice.of(50),
            listed_by=PlayerId(100),
        )

        handler.handle_shop_item_listed(event)

        assert listing_repo.find_by_id(ShopListingId(101)) is None

    def test_handle_shop_item_unlisted(self, setup_handler):
        """取り下げイベントでリストReadModelが削除され、サマリのlisting_countが減る"""
        handler, summary_repo, listing_repo, _, _ = setup_handler

        from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import (
            ShopListingReadModel,
        )
        from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import (
            ShopSummaryReadModel,
        )

        summary_rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Shop",
            description="",
            owner_ids=[PlayerId(100)],
            listing_count=1,
            created_at=datetime.now(),
        )
        summary_repo.save(summary_rm)

        listing_rm = ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            item_name="Sword",
            item_spec_id=1,
            price_per_unit=100,
            quantity=1,
            listed_by=PlayerId(100),
        )
        listing_repo.save(listing_rm)

        event = ShopItemUnlistedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(101),
            unlisted_by=PlayerId(100),
        )

        handler.handle_shop_item_unlisted(event)

        assert listing_repo.find_by_id(ShopListingId(101)) is None
        summary = summary_repo.find_by_id(ShopId(1))
        assert summary is not None
        assert summary.listing_count == 0

    def test_handle_shop_item_purchased_decrements_quantity(self, setup_handler):
        """購入イベントで在庫が減り、0でなければリストが残る"""
        handler, summary_repo, listing_repo, _, _ = setup_handler

        from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import (
            ShopListingReadModel,
        )
        from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import (
            ShopSummaryReadModel,
        )

        summary_rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Shop",
            description="",
            owner_ids=[PlayerId(100)],
            listing_count=1,
            created_at=datetime.now(),
        )
        summary_repo.save(summary_rm)

        listing_rm = ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            item_name="Sword",
            item_spec_id=1,
            price_per_unit=100,
            quantity=10,
            listed_by=PlayerId(100),
        )
        listing_repo.save(listing_rm)

        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            buyer_id=PlayerId(201),
            quantity=3,
            total_gold=300,
            seller_id=PlayerId(100),
        )

        handler.handle_shop_item_purchased(event)

        listing = listing_repo.find_by_id(ShopListingId(101))
        assert listing is not None
        assert listing.quantity == 7
        summary = summary_repo.find_by_id(ShopId(1))
        assert summary is not None
        assert summary.listing_count == 1

    def test_handle_shop_item_purchased_quantity_zero_removes_listing(self, setup_handler):
        """購入で在庫が0になるとリストが削除され、サマリのlisting_countが減る"""
        handler, summary_repo, listing_repo, _, _ = setup_handler

        from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import (
            ShopListingReadModel,
        )
        from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import (
            ShopSummaryReadModel,
        )

        summary_rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Shop",
            description="",
            owner_ids=[PlayerId(100)],
            listing_count=1,
            created_at=datetime.now(),
        )
        summary_repo.save(summary_rm)

        listing_rm = ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            item_name="Sword",
            item_spec_id=1,
            price_per_unit=100,
            quantity=3,
            listed_by=PlayerId(100),
        )
        listing_repo.save(listing_rm)

        event = ShopItemPurchasedEvent.create(
            aggregate_id=ShopId(1),
            aggregate_type="ShopAggregate",
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            buyer_id=PlayerId(201),
            quantity=3,
            total_gold=300,
            seller_id=PlayerId(100),
        )

        handler.handle_shop_item_purchased(event)

        assert listing_repo.find_by_id(ShopListingId(101)) is None
        summary = summary_repo.find_by_id(ShopId(1))
        assert summary is not None
        assert summary.listing_count == 0
