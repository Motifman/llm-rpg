import pytest
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.aggregate.world_map_aggregate import WorldMapAggregate
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.connection import Connection
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy


class TestGlobalPathfindingService:
    @pytest.fixture
    def service(self):
        return GlobalPathfindingService(PathfindingService(AStarPathfindingStrategy()))

    def _create_simple_map(self, spot_id: int, gateways=None):
        tiles = []
        for x in range(10):
            for y in range(10):
                tiles.append(Tile(Coordinate(x, y), TerrainType.grass()))
        return PhysicalMapAggregate.create(SpotId(spot_id), tiles, gateways=gateways)

    def test_calculate_global_path_same_spot(self, service):
        spot_id = SpotId(1)
        phys_map = self._create_simple_map(1)
        world_map = WorldMapAggregate(WorldId(1), spots=[Spot(spot_id, "Home", "")])
        
        goal, path = service.calculate_global_path(
            current_spot_id=spot_id,
            current_coord=Coordinate(0, 0),
            target_spot_id=spot_id,
            target_coord=Coordinate(2, 2),
            physical_map=phys_map,
            world_map=world_map,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )
        
        assert goal == Coordinate(2, 2)
        assert len(path) > 0
        assert path[-1] == Coordinate(2, 2)

    def test_calculate_global_path_direct_neighbor(self, service):
        spot1_id = SpotId(1)
        spot2_id = SpotId(2)
        
        gateway = Gateway(
            GatewayId(101), "To Spot 2", 
            RectArea.from_coordinates(Coordinate(5, 5), Coordinate(5, 5)),
            spot2_id, Coordinate(0, 0)
        )
        
        phys_map1 = self._create_simple_map(1, gateways=[gateway])
        world_map = WorldMapAggregate(
            WorldId(1), 
            spots=[Spot(spot1_id, "S1", ""), Spot(spot2_id, "S2", "")],
            connections=[Connection(spot1_id, spot2_id)]
        )
        
        goal, path = service.calculate_global_path(
            current_spot_id=spot1_id,
            current_coord=Coordinate(0, 0),
            target_spot_id=spot2_id,
            target_coord=Coordinate(10, 10), # Far away in another spot
            physical_map=phys_map1,
            world_map=world_map,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )
        
        # Should target the gateway coordinate
        assert goal == Coordinate(5, 5)
        assert len(path) > 0
        assert path[-1] == Coordinate(5, 5)

    def test_calculate_global_path_multi_hop(self, service):
        spot1_id = SpotId(1)
        spot2_id = SpotId(2)
        spot3_id = SpotId(3)
        
        # Gateway to S2
        gateway = Gateway(
            GatewayId(101), "To Spot 2", 
            RectArea.from_coordinates(Coordinate(5, 5), Coordinate(5, 5)),
            spot2_id, Coordinate(0, 0)
        )
        
        phys_map1 = self._create_simple_map(1, gateways=[gateway])
        world_map = WorldMapAggregate(
            WorldId(1), 
            spots=[Spot(spot1_id, "S1", ""), Spot(spot2_id, "S2", ""), Spot(spot3_id, "S3", "")],
            connections=[
                Connection(spot1_id, spot2_id),
                Connection(spot2_id, spot3_id)
            ]
        )
        
        # Target is S3, which is not directly connected to S1
        goal, path = service.calculate_global_path(
            current_spot_id=spot1_id,
            current_coord=Coordinate(0, 0),
            target_spot_id=spot3_id,
            target_coord=Coordinate(10, 10),
            physical_map=phys_map1,
            world_map=world_map,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )
        
        # BFS should find that to get to S3, we must first go to S2.
        # So it should target the gateway to S2.
        assert goal == Coordinate(5, 5)
        assert len(path) > 0
        assert path[-1] == Coordinate(5, 5)

    def test_calculate_global_path_no_connection(self, service):
        spot1_id = SpotId(1)
        spot3_id = SpotId(3)
        
        phys_map1 = self._create_simple_map(1)
        world_map = WorldMapAggregate(
            WorldId(1), 
            spots=[Spot(spot1_id, "S1", ""), Spot(spot3_id, "S3", "")]
        )
        
        goal, path = service.calculate_global_path(
            current_spot_id=spot1_id,
            current_coord=Coordinate(0, 0),
            target_spot_id=spot3_id,
            target_coord=Coordinate(10, 10),
            physical_map=phys_map1,
            world_map=world_map,
            world_object_id=WorldObjectId.create(1),
            capability=MovementCapability.normal_walk()
        )
        
        assert goal is None
        assert path == []
