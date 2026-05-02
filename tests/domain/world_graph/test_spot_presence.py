import pytest

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import SpotPresenceInvariantException
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_presence import SpotPresence


class TestSpotPresence:
    @pytest.fixture
    def spot(self) -> SpotId:
        return SpotId.create(1)

    @pytest.fixture
    def e1(self) -> EntityId:
        return EntityId.create(1)

    @pytest.fixture
    def e2(self) -> EntityId:
        return EntityId.create(2)

    def test_empty(self, spot):
        p = SpotPresence.empty(spot)
        assert p.count() == 0
        assert not p.is_present(EntityId.create(1))

    def test_add_remove(self, spot, e1, e2):
        p = SpotPresence.empty(spot).add(e1).add(e2)
        assert p.count() == 2
        p2 = p.remove(e1)
        assert p2.count() == 1
        assert not p2.is_present(e1)
        assert p2.is_present(e2)

    def test_duplicate_add_raises(self, spot, e1):
        p = SpotPresence.empty(spot).add(e1)
        with pytest.raises(SpotPresenceInvariantException):
            p.add(e1)

    def test_remove_missing_raises(self, spot, e1):
        p = SpotPresence.empty(spot)
        with pytest.raises(SpotPresenceInvariantException):
            p.remove(e1)
