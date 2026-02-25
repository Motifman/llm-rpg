"""LocationEstablishmentAggregate のテスト"""
import pytest

from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.enum.world_enum import EstablishmentType
from ai_rpg_world.domain.world.event.location_establishment_events import (
    LocationEstablishmentClaimedEvent,
    LocationEstablishmentReleasedEvent,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    LocationAlreadyOccupiedException,
    LocationNotOccupiedException,
)


class TestLocationEstablishmentAggregate:
    """LocationEstablishmentAggregate のテスト"""

    @pytest.fixture
    def spot_id(self) -> SpotId:
        return SpotId.create(1)

    @pytest.fixture
    def location_area_id(self) -> LocationAreaId:
        return LocationAreaId.create(1)

    @pytest.fixture
    def slot(self, spot_id, location_area_id) -> LocationEstablishmentAggregate:
        return LocationEstablishmentAggregate.create(
            spot_id=spot_id,
            location_area_id=location_area_id,
        )

    class TestCreate:
        def test_create_success(self, spot_id, location_area_id):
            slot = LocationEstablishmentAggregate.create(
                spot_id=spot_id,
                location_area_id=location_area_id,
            )
            assert slot.id.spot_id == spot_id
            assert slot.id.location_area_id == location_area_id
            assert slot.spot_id == spot_id
            assert slot.location_area_id == location_area_id
            assert slot.establishment_type is None
            assert slot.establishment_id is None
            assert slot.is_occupied() is False
            assert len(slot.get_events()) == 0

        def test_create_different_locations_different_ids(self):
            s1 = LocationEstablishmentAggregate.create(
                SpotId.create(1), LocationAreaId.create(1)
            )
            s2 = LocationEstablishmentAggregate.create(
                SpotId.create(2), LocationAreaId.create(1)
            )
            assert s1.id != s2.id

    class TestClaim:
        def test_claim_success(self, slot):
            slot.claim(EstablishmentType.SHOP, 10)
            assert slot.establishment_type == EstablishmentType.SHOP
            assert slot.establishment_id == 10
            assert slot.is_occupied() is True
            events = slot.get_events()
            assert len(events) == 1
            assert isinstance(events[0], LocationEstablishmentClaimedEvent)
            assert events[0].establishment_type == EstablishmentType.SHOP
            assert events[0].establishment_id == 10

        def test_claim_twice_raises(self, slot):
            slot.claim(EstablishmentType.SHOP, 10)
            with pytest.raises(LocationAlreadyOccupiedException) as exc_info:
                slot.claim(EstablishmentType.GUILD, 20)
            assert "already occupied" in str(exc_info.value).lower() or "LOCATION_ALREADY_OCCUPIED" in str(exc_info.value)

        def test_claim_guild_success(self, spot_id, location_area_id):
            slot = LocationEstablishmentAggregate.create(spot_id, location_area_id)
            slot.claim(EstablishmentType.GUILD, 5)
            assert slot.establishment_type == EstablishmentType.GUILD
            assert slot.establishment_id == 5

    class TestRelease:
        def test_release_success(self, slot):
            slot.claim(EstablishmentType.SHOP, 10)
            slot.clear_events()
            slot.release()
            assert slot.establishment_type is None
            assert slot.establishment_id is None
            assert slot.is_occupied() is False
            events = slot.get_events()
            assert len(events) == 1
            assert isinstance(events[0], LocationEstablishmentReleasedEvent)
            assert events[0].previous_establishment_type == EstablishmentType.SHOP
            assert events[0].previous_establishment_id == 10

        def test_release_when_not_occupied_raises(self, slot):
            with pytest.raises(LocationNotOccupiedException) as exc_info:
                slot.release()
            assert "not occupied" in str(exc_info.value).lower() or "LOCATION_NOT_OCCUPIED" in str(exc_info.value)

        def test_release_after_release_raises(self, slot):
            slot.claim(EstablishmentType.SHOP, 10)
            slot.release()
            with pytest.raises(LocationNotOccupiedException):
                slot.release()

    class TestReclaimAfterRelease:
        def test_release_then_claim_same_slot_success(self, slot):
            slot.claim(EstablishmentType.SHOP, 10)
            slot.release()
            slot.clear_events()
            slot.claim(EstablishmentType.GUILD, 20)
            assert slot.establishment_type == EstablishmentType.GUILD
            assert slot.establishment_id == 20
            events = slot.get_events()
            assert len(events) == 1
            assert isinstance(events[0], LocationEstablishmentClaimedEvent)
