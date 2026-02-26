import pytest
from typing import List, Dict
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.connected_spots_provider import IConnectedSpotsProvider
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy


class _DictConnectedSpotsProvider(IConnectedSpotsProvider):
    """テスト用: 辞書で接続を定義する IConnectedSpotsProvider の簡易実装"""

    def __init__(self, connections: Dict[int, List[int]]):
        # connections: from_spot_id -> [to_spot_id, ...]
        self._connections = {
            SpotId(sid): [SpotId(t) for t in to_list]
            for sid, to_list in connections.items()
        }

    def get_connected_spots(self, spot_id: SpotId) -> List[SpotId]:
        return self._connections.get(spot_id, [])


class TestGlobalPathfindingService:
    @pytest.fixture
    def service(self):
        return GlobalPathfindingService(PathfindingService(AStarPathfindingStrategy()))

    def _create_simple_map(self, spot_id: int, gateways=None):
        tiles = []
        for x in range(10):
            for y in range(10):
                tiles.append(Tile(Coordinate(x, y, 0), TerrainType.grass()))
        return PhysicalMapAggregate.create(SpotId(spot_id), tiles, gateways=gateways)

    def test_calculate_global_path_same_spot(self, service):
        spot_id = SpotId(1)
        phys_map = self._create_simple_map(1)
        provider = _DictConnectedSpotsProvider({})

        goal, path = service.calculate_global_path(
            current_spot_id=spot_id,
            current_coord=Coordinate(0, 0, 0),
            target_spot_id=spot_id,
            target_coord=Coordinate(2, 2, 0),
            physical_map=phys_map,
            connected_spots_provider=provider,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )

        assert goal == Coordinate(2, 2, 0)
        assert len(path) > 0
        assert path[-1] == Coordinate(2, 2, 0)

    def test_calculate_global_path_direct_neighbor(self, service):
        spot1_id = SpotId(1)
        spot2_id = SpotId(2)

        gateway = Gateway(
            GatewayId(101), "To Spot 2",
            RectArea.from_coordinates(Coordinate(5, 5, 0), Coordinate(5, 5, 0)),
            spot2_id, Coordinate(0, 0, 0)
        )

        phys_map1 = self._create_simple_map(1, gateways=[gateway])
        provider = _DictConnectedSpotsProvider({1: [2]})

        goal, path = service.calculate_global_path(
            current_spot_id=spot1_id,
            current_coord=Coordinate(0, 0, 0),
            target_spot_id=spot2_id,
            target_coord=Coordinate(10, 10, 0),
            physical_map=phys_map1,
            connected_spots_provider=provider,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )

        assert goal == Coordinate(5, 5, 0)
        assert len(path) > 0
        assert path[-1] == Coordinate(5, 5, 0)

    def test_calculate_global_path_multi_hop(self, service):
        spot1_id = SpotId(1)
        spot2_id = SpotId(2)
        spot3_id = SpotId(3)

        gateway = Gateway(
            GatewayId(101), "To Spot 2",
            RectArea.from_coordinates(Coordinate(5, 5, 0), Coordinate(5, 5, 0)),
            spot2_id, Coordinate(0, 0, 0)
        )

        phys_map1 = self._create_simple_map(1, gateways=[gateway])
        provider = _DictConnectedSpotsProvider({1: [2], 2: [3]})

        goal, path = service.calculate_global_path(
            current_spot_id=spot1_id,
            current_coord=Coordinate(0, 0, 0),
            target_spot_id=spot3_id,
            target_coord=Coordinate(10, 10, 0),
            physical_map=phys_map1,
            connected_spots_provider=provider,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )

        assert goal == Coordinate(5, 5, 0)
        assert len(path) > 0
        assert path[-1] == Coordinate(5, 5, 0)

    def test_calculate_global_path_no_connection(self, service):
        spot1_id = SpotId(1)
        spot3_id = SpotId(3)

        phys_map1 = self._create_simple_map(1)
        provider = _DictConnectedSpotsProvider({1: []})  # 1 から 3 への接続なし

        goal, path = service.calculate_global_path(
            current_spot_id=spot1_id,
            current_coord=Coordinate(0, 0, 0),
            target_spot_id=spot3_id,
            target_coord=Coordinate(10, 10, 0),
            physical_map=phys_map1,
            connected_spots_provider=provider,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )

        assert goal is None
        assert path == []
