"""InMemoryLocationEstablishmentRepository のテスト"""
import pytest

from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.enum.world_enum import EstablishmentType
from ai_rpg_world.infrastructure.repository.in_memory_location_establishment_repository import (
    InMemoryLocationEstablishmentRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


class TestInMemoryLocationEstablishmentRepository:
    """InMemoryLocationEstablishmentRepository のテスト"""

    @pytest.fixture
    def data_store(self) -> InMemoryDataStore:
        return InMemoryDataStore()

    @pytest.fixture
    def repo(self, data_store) -> InMemoryLocationEstablishmentRepository:
        return InMemoryLocationEstablishmentRepository(data_store=data_store)

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId.create(1)

    @pytest.fixture
    def location_area_id(self) -> LocationAreaId:
        return LocationAreaId.create(1)

    def test_save_and_find_by_id(self, repo, spot_id, location_area_id):
        """保存した集約を find_by_id で取得できる"""
        slot = LocationEstablishmentAggregate.create(
            spot_id=spot_id,
            location_area_id=location_area_id,
        )
        repo.save(slot)
        slot_id = LocationSlotId(spot_id=spot_id, location_area_id=location_area_id)
        found = repo.find_by_id(slot_id)
        assert found is not None
        assert found.spot_id == spot_id
        assert found.location_area_id == location_area_id
        assert found.is_occupied() is False

    def test_find_by_spot_and_location(self, repo, spot_id, location_area_id):
        """find_by_spot_and_location で取得できる"""
        slot = LocationEstablishmentAggregate.create(
            spot_id=spot_id,
            location_area_id=location_area_id,
        )
        slot.claim(EstablishmentType.SHOP, 10)
        repo.save(slot)
        found = repo.find_by_spot_and_location(spot_id, location_area_id)
        assert found is not None
        assert found.establishment_type == EstablishmentType.SHOP
        assert found.establishment_id == 10

    def test_find_by_spot_and_location_returns_none_when_missing(
        self, repo, spot_id, location_area_id
    ):
        """存在しないロケーションは None"""
        found = repo.find_by_spot_and_location(spot_id, location_area_id)
        assert found is None

    def test_find_all(self, repo, spot_id, location_area_id):
        """find_all で全件取得できる"""
        s1 = LocationEstablishmentAggregate.create(spot_id, location_area_id)
        repo.save(s1)
        s2 = LocationEstablishmentAggregate.create(
            SpotId.create(2), LocationAreaId.create(2)
        )
        repo.save(s2)
        all_slots = repo.find_all()
        assert len(all_slots) == 2

    def test_delete(self, repo, spot_id, location_area_id):
        """delete で削除できる"""
        slot = LocationEstablishmentAggregate.create(spot_id, location_area_id)
        repo.save(slot)
        slot_id = LocationSlotId(spot_id=spot_id, location_area_id=location_area_id)
        result = repo.delete(slot_id)
        assert result is True
        assert repo.find_by_id(slot_id) is None

    def test_delete_nonexistent_returns_false(self, repo, spot_id, location_area_id):
        """存在しない ID で delete は False"""
        slot_id = LocationSlotId(spot_id=spot_id, location_area_id=location_area_id)
        result = repo.delete(slot_id)
        assert result is False

    def test_find_by_ids(self, repo, spot_id, location_area_id):
        """find_by_ids で複数取得できる"""
        slot = LocationEstablishmentAggregate.create(spot_id, location_area_id)
        repo.save(slot)
        slot_id = LocationSlotId(spot_id=spot_id, location_area_id=location_area_id)
        found_list = repo.find_by_ids([slot_id])
        assert len(found_list) == 1
        assert found_list[0].id == slot_id
