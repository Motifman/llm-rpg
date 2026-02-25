"""InMemoryShopSummaryReadModelRepositoryのテスト"""
import pytest
from datetime import datetime

from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import (
    ShopSummaryReadModel,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_shop_summary_read_model_repository import (
    InMemoryShopSummaryReadModelRepository,
)


class TestInMemoryShopSummaryReadModelRepository:
    """InMemoryShopSummaryReadModelRepositoryのテストクラス"""

    @pytest.fixture
    def repository(self):
        return InMemoryShopSummaryReadModelRepository()

    @pytest.fixture
    def sample_summary(self):
        return ShopSummaryReadModel.create(
            shop_id=ShopId(1),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(20),
            name="Test Shop",
            description="Description",
            owner_ids=[PlayerId(100), PlayerId(101)],
            listing_count=3,
            created_at=datetime.now(),
        )

    def test_save_and_find_by_id(self, repository, sample_summary):
        """保存後、find_by_idで取得できる"""
        repository.save(sample_summary)
        found = repository.find_by_id(ShopId(1))
        assert found is not None
        assert found.shop_id == 1
        assert found.name == "Test Shop"
        assert found.listing_count == 3

    def test_find_by_id_returns_none_when_not_exists(self, repository):
        """存在しないIDではNone"""
        assert repository.find_by_id(ShopId(999)) is None

    def test_find_by_ids(self, repository, sample_summary):
        """find_by_idsで複数取得できる"""
        repository.save(sample_summary)
        other = ShopSummaryReadModel.create(
            shop_id=ShopId(2),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(21),
            name="Other",
            description="",
            owner_ids=[PlayerId(102)],
            listing_count=0,
            created_at=datetime.now(),
        )
        repository.save(other)
        result = repository.find_by_ids([ShopId(1), ShopId(2), ShopId(999)])
        assert len(result) == 2
        ids = {r.shop_id for r in result}
        assert ids == {1, 2}

    def test_delete(self, repository, sample_summary):
        """削除後はfind_by_idでNone"""
        repository.save(sample_summary)
        assert repository.delete(ShopId(1)) is True
        assert repository.find_by_id(ShopId(1)) is None

    def test_delete_nonexistent_returns_false(self, repository):
        """存在しないIDの削除はFalse"""
        assert repository.delete(ShopId(999)) is False

    def test_find_all(self, repository, sample_summary):
        """find_allで全件取得"""
        repository.save(sample_summary)
        other = ShopSummaryReadModel.create(
            shop_id=ShopId(2),
            spot_id=SpotId(11),
            location_area_id=LocationAreaId(22),
            name="O",
            description="",
            owner_ids=[PlayerId(102)],
            listing_count=0,
            created_at=datetime.now(),
        )
        repository.save(other)
        result = repository.find_all()
        assert len(result) == 2

    def test_find_by_spot_and_location(self, repository, sample_summary):
        """find_by_spot_and_locationで一致するショップを取得"""
        repository.save(sample_summary)
        found = repository.find_by_spot_and_location(SpotId(10), LocationAreaId(20))
        assert found is not None
        assert found.shop_id == 1

    def test_find_by_spot_and_location_returns_none_when_not_exists(self, repository):
        """該当ロケーションにショップが無いときはNone"""
        assert repository.find_by_spot_and_location(
            SpotId(1), LocationAreaId(1)
        ) is None

    def test_find_all_by_spot_id(self, repository, sample_summary):
        """find_all_by_spot_idで同一スポットのショップ一覧"""
        repository.save(sample_summary)
        other = ShopSummaryReadModel.create(
            shop_id=ShopId(2),
            spot_id=SpotId(10),
            location_area_id=LocationAreaId(21),
            name="O",
            description="",
            owner_ids=[PlayerId(102)],
            listing_count=0,
            created_at=datetime.now(),
        )
        repository.save(other)
        result = repository.find_all_by_spot_id(SpotId(10))
        assert len(result) == 2
        result = repository.find_all_by_spot_id(SpotId(99))
        assert len(result) == 0
