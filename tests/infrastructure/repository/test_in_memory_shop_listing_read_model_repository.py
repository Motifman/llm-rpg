"""InMemoryShopListingReadModelRepositoryのテスト"""
import pytest
from datetime import datetime

from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import (
    ShopListingReadModel,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.infrastructure.repository.in_memory_shop_listing_read_model_repository import (
    InMemoryShopListingReadModelRepository,
)


class TestInMemoryShopListingReadModelRepository:
    """InMemoryShopListingReadModelRepositoryのテストクラス"""

    @pytest.fixture
    def repository(self):
        return InMemoryShopListingReadModelRepository()

    @pytest.fixture
    def sample_listing(self):
        return ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(101),
            item_instance_id=ItemInstanceId(200),
            item_name="Test Sword",
            item_spec_id=5,
            price_per_unit=100,
            quantity=10,
            listed_by=PlayerId(100),
            listed_at=datetime.now(),
        )

    def test_save_and_find_by_id(self, repository, sample_listing):
        """保存後、find_by_idで取得できる"""
        repository.save(sample_listing)
        found = repository.find_by_id(ShopListingId(101))
        assert found is not None
        assert found.listing_id == 101
        assert found.item_name == "Test Sword"
        assert found.quantity == 10

    def test_find_by_id_returns_none_when_not_exists(self, repository):
        """存在しないlisting_idではNone"""
        assert repository.find_by_id(ShopListingId(999)) is None

    def test_find_by_shop_id(self, repository, sample_listing):
        """find_by_shop_idでショップの出品一覧を取得"""
        repository.save(sample_listing)
        other = ShopListingReadModel.create(
            shop_id=ShopId(1),
            listing_id=ShopListingId(102),
            item_instance_id=ItemInstanceId(201),
            item_name="Potion",
            item_spec_id=6,
            price_per_unit=50,
            quantity=5,
            listed_by=PlayerId(100),
        )
        repository.save(other)
        result = repository.find_by_shop_id(ShopId(1))
        assert len(result) == 2
        listing_ids = {r.listing_id for r in result}
        assert listing_ids == {101, 102}

    def test_find_by_shop_id_empty_when_none(self, repository):
        """ショップに出品が無いときは空リスト"""
        assert repository.find_by_shop_id(ShopId(1)) == []

    def test_delete(self, repository, sample_listing):
        """削除後はfind_by_idでNone"""
        repository.save(sample_listing)
        assert repository.delete(ShopListingId(101)) is True
        assert repository.find_by_id(ShopListingId(101)) is None

    def test_delete_nonexistent_returns_false(self, repository):
        """存在しないIDの削除はFalse"""
        assert repository.delete(ShopListingId(999)) is False

    def test_find_by_ids(self, repository, sample_listing):
        """find_by_idsで複数取得できる"""
        repository.save(sample_listing)
        other = ShopListingReadModel.create(
            shop_id=ShopId(2),
            listing_id=ShopListingId(102),
            item_instance_id=ItemInstanceId(201),
            item_name="P",
            item_spec_id=1,
            price_per_unit=1,
            quantity=1,
            listed_by=PlayerId(101),
        )
        repository.save(other)
        result = repository.find_by_ids(
            [ShopListingId(101), ShopListingId(102), ShopListingId(999)]
        )
        assert len(result) == 2

    def test_find_all(self, repository, sample_listing):
        """find_allで全件取得"""
        repository.save(sample_listing)
        result = repository.find_all()
        assert len(result) == 1
        assert result[0].listing_id == 101
