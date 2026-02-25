"""ShopQueryServiceのテスト"""
import pytest
from datetime import datetime

from ai_rpg_world.application.shop.services.shop_query_service import ShopQueryService
from ai_rpg_world.application.shop.contracts.dtos import (
    ShopSummaryDto,
    ShopListingDto,
    ShopDetailDto,
)
from ai_rpg_world.application.shop.exceptions.query_exception import (
    ShopQueryApplicationException,
)
from ai_rpg_world.application.common.exceptions import SystemErrorException

from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import (
    ShopSummaryReadModel,
)
from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import (
    ShopListingReadModel,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId

from ai_rpg_world.infrastructure.repository.in_memory_shop_summary_read_model_repository import (
    InMemoryShopSummaryReadModelRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_shop_listing_read_model_repository import (
    InMemoryShopListingReadModelRepository,
)


class TestShopQueryService:
    """ShopQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.summary_repo = InMemoryShopSummaryReadModelRepository()
        self.listing_repo = InMemoryShopListingReadModelRepository()
        self.service = ShopQueryService(
            shop_summary_read_model_repository=self.summary_repo,
            shop_listing_read_model_repository=self.listing_repo,
        )

    def test_get_shops_at_location_returns_empty_when_none(self):
        """ロケーションにショップが無いときは空リスト"""
        result = self.service.get_shops_at_location(spot_id=1, location_area_id=1)
        assert result == []

    def test_get_shops_at_location_returns_shop_when_exists(self):
        """ロケーションにショップがあるときはサマリが返る"""
        rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="My Shop",
            description="Desc",
            owner_ids=[PlayerId(100)],
            listing_count=2,
            created_at=datetime.now(),
        )
        self.summary_repo.save(rm)

        result = self.service.get_shops_at_location(spot_id=10, location_area_id=20)
        assert len(result) == 1
        assert isinstance(result[0], ShopSummaryDto)
        assert result[0].shop_id == 1
        assert result[0].name == "My Shop"
        assert result[0].listing_count == 2

    def test_get_shops_at_location_invalid_spot_id_raises(self):
        """無効なspot_idではドメイン例外がクエリ例外に変換される"""
        with pytest.raises(ShopQueryApplicationException):
            self.service.get_shops_at_location(spot_id=0, location_area_id=1)

    def test_get_shops_at_location_invalid_location_area_id_raises(self):
        """無効なlocation_area_idではドメイン例外がクエリ例外に変換される"""
        with pytest.raises(ShopQueryApplicationException):
            self.service.get_shops_at_location(spot_id=1, location_area_id=0)

    def test_get_shop_detail_success(self):
        """存在するショップの詳細が取得できる"""
        summary_rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Shop",
            description="D",
            owner_ids=[PlayerId(100)],
            listing_count=1,
            created_at=datetime.now(),
        )
        self.summary_repo.save(summary_rm)
        listing_rm = ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            item_name="Sword",
            item_spec_id=1,
            price_per_unit=100,
            quantity=5,
            listed_by=PlayerId(100),
        )
        self.listing_repo.save(listing_rm)

        result = self.service.get_shop_detail(shop_id=1)
        assert isinstance(result, ShopDetailDto)
        assert result.summary.shop_id == 1
        assert result.summary.name == "Shop"
        assert len(result.listings) == 1
        assert result.listings[0].item_name == "Sword"
        assert result.listings[0].quantity == 5

    def test_get_shop_detail_not_found_raises(self):
        """存在しないショップIDではShopQueryApplicationException"""
        with pytest.raises(ShopQueryApplicationException) as exc_info:
            self.service.get_shop_detail(shop_id=999)
        assert "999" in str(exc_info.value)

    def test_get_shop_detail_invalid_shop_id_raises(self):
        """無効なshop_idではドメイン例外がクエリ例外に変換される"""
        with pytest.raises(ShopQueryApplicationException):
            self.service.get_shop_detail(shop_id=0)

    def test_get_shop_summary_success(self):
        """存在するショップのサマリが取得できる"""
        rm = ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="S",
            description="D",
            owner_ids=[PlayerId(100)],
            listing_count=0,
            created_at=datetime.now(),
        )
        self.summary_repo.save(rm)
        result = self.service.get_shop_summary(shop_id=1)
        assert isinstance(result, ShopSummaryDto)
        assert result.shop_id == 1
        assert result.name == "S"

    def test_get_shop_summary_not_found_raises(self):
        """存在しないショップではShopQueryApplicationException"""
        with pytest.raises(ShopQueryApplicationException):
            self.service.get_shop_summary(shop_id=999)

    def test_get_listings_for_shop_empty(self):
        """出品が無いショップでは空リスト"""
        result = self.service.get_listings_for_shop(shop_id=1)
        assert result == []

    def test_get_listings_for_shop_returns_listings(self):
        """出品があるショップではリストが返る"""
        listing_rm = ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            item_name="Potion",
            item_spec_id=2,
            price_per_unit=50,
            quantity=10,
            listed_by=PlayerId(100),
        )
        self.listing_repo.save(listing_rm)
        result = self.service.get_listings_for_shop(shop_id=1)
        assert len(result) == 1
        assert result[0].item_name == "Potion"
        assert result[0].price_per_unit == 50

    def test_get_listings_for_shop_invalid_shop_id_raises(self):
        """無効なshop_idではドメイン例外がクエリ例外に変換される"""
        with pytest.raises(ShopQueryApplicationException):
            self.service.get_listings_for_shop(shop_id=-1)

    def test_execute_with_error_handling_domain_exception(self):
        """ドメイン例外が発生した場合、ShopQueryApplicationExceptionに変換される"""
        from ai_rpg_world.domain.common.exception import StateException

        def raise_domain():
            raise StateException("Test domain error")

        with pytest.raises(ShopQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=raise_domain,
                context={"action": "test"},
            )
        assert "Domain error" in str(exc_info.value)

    def test_execute_with_error_handling_application_exception(self):
        """ShopQueryApplicationExceptionはそのまま再スローされる"""
        app_exception = ShopQueryApplicationException.shop_not_found(1)

        def raise_app():
            raise app_exception

        with pytest.raises(ShopQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=raise_app,
                context={"action": "test"},
            )
        assert exc_info.value is app_exception

    def test_execute_with_error_handling_unexpected_exception(self):
        """予期しない例外はSystemErrorExceptionに変換される"""
        def raise_value():
            raise ValueError("Unexpected")

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=raise_value,
                context={"action": "test_action"},
            )
        assert "test_action failed" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, ValueError)
