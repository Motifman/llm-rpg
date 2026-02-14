"""AllegianceService のテスト"""

import pytest
from ai_rpg_world.domain.world.service.allegiance_service import PackAllegianceService
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent


class TestPackAllegianceService:
    @pytest.fixture
    def service(self):
        return PackAllegianceService()

    def test_same_pack_is_ally(self, service):
        pack = PackId.create("p1")
        a = AutonomousBehaviorComponent(pack_id=pack)
        b = AutonomousBehaviorComponent(pack_id=pack)
        assert service.is_ally(a, b) is True

    def test_different_pack_not_ally(self, service):
        a = AutonomousBehaviorComponent(pack_id=PackId.create("p1"))
        b = AutonomousBehaviorComponent(pack_id=PackId.create("p2"))
        assert service.is_ally(a, b) is False

    def test_none_pack_not_ally(self, service):
        a = AutonomousBehaviorComponent(pack_id=PackId.create("p1"))
        b = AutonomousBehaviorComponent()
        assert service.is_ally(a, b) is False
        assert service.is_ally(b, a) is False

    def test_both_none_pack_not_ally(self, service):
        a = AutonomousBehaviorComponent()
        b = AutonomousBehaviorComponent()
        assert service.is_ally(a, b) is False

    def test_actor_component_without_pack_not_ally(self, service):
        """ActorComponent（pack_id なし）同士は味方ではない"""
        a = ActorComponent(race="human")
        b = ActorComponent(race="human")
        assert service.is_ally(a, b) is False
