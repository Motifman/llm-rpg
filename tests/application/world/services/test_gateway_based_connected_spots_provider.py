"""GatewayBasedConnectedSpotsProvider のテスト（正常・境界ケース）"""

import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)


def _make_tiles(width: int = 5, height: int = 5):
    return [
        Tile(Coordinate(x, y, 0), TerrainType.grass())
        for x in range(width) for y in range(height)
    ]


class TestGatewayBasedConnectedSpotsProvider:
    """GatewayBasedConnectedSpotsProvider のテスト"""

    @pytest.fixture
    def data_store(self):
        ds = InMemoryDataStore()
        ds.clear_all()
        return ds

    @pytest.fixture
    def map_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store=data_store)

    @pytest.fixture
    def provider(self, map_repo):
        return GatewayBasedConnectedSpotsProvider(map_repo)

    def test_get_connected_spots_empty_when_no_maps(self, provider):
        """物理マップが1つもないときは空リスト"""
        assert provider.get_connected_spots(SpotId(1)) == []

    def test_get_connected_spots_empty_when_spot_has_no_gateways(self, map_repo, provider):
        """該当スポットにゲートウェイがなければ空リスト"""
        pmap = PhysicalMapAggregate.create(SpotId(1), _make_tiles())
        map_repo.save(pmap)
        assert provider.get_connected_spots(SpotId(1)) == []

    def test_get_connected_spots_returns_target_spot_ids(self, map_repo, provider):
        """ゲートウェイの target_spot_id が接続として返る"""
        gw = Gateway(
            gateway_id=GatewayId(101),
            name="To 2",
            area=PointArea(Coordinate(2, 2, 0)),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
        )
        pmap = PhysicalMapAggregate.create(SpotId(1), _make_tiles(), gateways=[gw])
        map_repo.save(pmap)
        connected = provider.get_connected_spots(SpotId(1))
        assert connected == [SpotId(2)]

    def test_get_connected_spots_multiple_gateways_deduplicated(self, map_repo, provider):
        """同一 target へのゲートウェイが複数あっても重複除去される"""
        gw1 = Gateway(
            GatewayId(101), "To 2a", PointArea(Coordinate(1, 1, 0)), SpotId(2), Coordinate(0, 0, 0)
        )
        gw2 = Gateway(
            GatewayId(102), "To 2b", PointArea(Coordinate(2, 2, 0)), SpotId(2), Coordinate(0, 0, 0)
        )
        pmap = PhysicalMapAggregate.create(SpotId(1), _make_tiles(), gateways=[gw1, gw2])
        map_repo.save(pmap)
        connected = provider.get_connected_spots(SpotId(1))
        assert connected == [SpotId(2)]

    def test_get_connected_spots_multiple_maps_same_spot_id(self, map_repo, provider):
        """同一 spot_id のマップは1つのみ想定（最初に登録されたマップのゲートウェイが使われる）"""
        gw = Gateway(
            GatewayId(101), "To 2", PointArea(Coordinate(0, 0, 0)), SpotId(2), Coordinate(0, 0, 0)
        )
        pmap = PhysicalMapAggregate.create(SpotId(1), _make_tiles(), gateways=[gw])
        map_repo.save(pmap)
        assert provider.get_connected_spots(SpotId(1)) == [SpotId(2)]

    def test_get_connected_spots_two_maps_two_connections(self, map_repo, provider):
        """2つのマップがそれぞれゲートウェイを持つ場合、各 spot から接続が返る"""
        gw_1_to_2 = Gateway(
            GatewayId(101), "1->2", PointArea(Coordinate(1, 1, 0)), SpotId(2), Coordinate(0, 0, 0)
        )
        gw_2_to_3 = Gateway(
            GatewayId(102), "2->3", PointArea(Coordinate(1, 1, 0)), SpotId(3), Coordinate(0, 0, 0)
        )
        map1 = PhysicalMapAggregate.create(SpotId(1), _make_tiles(), gateways=[gw_1_to_2])
        map2 = PhysicalMapAggregate.create(SpotId(2), _make_tiles(), gateways=[gw_2_to_3])
        map_repo.save(map1)
        map_repo.save(map2)
        assert provider.get_connected_spots(SpotId(1)) == [SpotId(2)]
        assert provider.get_connected_spots(SpotId(2)) == [SpotId(3)]
        assert provider.get_connected_spots(SpotId(3)) == []
