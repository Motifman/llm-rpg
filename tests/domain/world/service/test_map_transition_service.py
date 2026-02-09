import pytest
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType


class TestMapTransitionService:
    @pytest.fixture
    def service(self):
        return MapTransitionService()

    def _create_sample_status(self, player_id: int, spot_id: int, x: int, y: int):
        exp_table = ExpTable(100, 1.5)
        return PlayerStatusAggregate(
            player_id=PlayerId(player_id),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0),
            planned_path=[Coordinate(x, y, 0), Coordinate(x+1, y, 0)] # Dummy path
        )

    def _create_simple_map(self, spot_id: int):
        tiles = []
        for x in range(5):
            for y in range(5):
                tiles.append(Tile(Coordinate(x, y), TerrainType.grass()))
        return PhysicalMapAggregate.create(SpotId(spot_id), tiles)

    def test_transition_player_updates_everything(self, service):
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        
        status = self._create_sample_status(player_id, spot1_id, 0, 0)
        phys_map1 = self._create_simple_map(spot1_id)
        phys_map2 = self._create_simple_map(spot2_id)
        
        # Add player object to map 1
        obj_id = WorldObjectId.create(player_id)
        player_obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.PLAYER)
        phys_map1.add_object(player_obj)
        
        landing_coord = Coordinate(3, 3)
        
        # When
        service.transition_player(status, phys_map1, phys_map2, landing_coord)
        
        # Then
        # 1. Map 1 should not have the player
        with pytest.raises(Exception):
            phys_map1.get_object(obj_id)
            
        # 2. Map 2 should have the player at landing coord
        new_obj = phys_map2.get_object(obj_id)
        assert new_obj.coordinate == landing_coord
        
        # 3. Player status should be updated
        assert status.current_spot_id == SpotId(spot2_id)
        assert status.current_coordinate == landing_coord
        
        # 4. Path should be cleared
        assert status.planned_path == []
        assert status.current_destination is None
