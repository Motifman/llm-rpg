"""Movement wiring（create_movement_application_service）のテスト。"""

import pytest

from ai_rpg_world.application.world.movement_wiring import create_movement_application_service
from ai_rpg_world.application.world.contracts.commands import MoveTileCommand
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.movement_config_service import DefaultMovementConfigService
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
    AStarPathfindingStrategy,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.enum.player_enum import Role


class TestCreateMovementApplicationService:
    """create_movement_application_service で構築したサービスが正常に動作することを検証する。"""

    def test_create_movement_application_service_produces_working_service(self):
        """create_movement_application_service が動作する MovementApplicationService を返すこと"""
        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        player_profile_repo = InMemoryPlayerProfileRepository(data_store, unit_of_work)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_repo = InMemorySpotRepository(data_store, unit_of_work)
        connected_spots_provider = GatewayBasedConnectedSpotsProvider(physical_map_repo)
        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        global_pathfinding_service = GlobalPathfindingService(pathfinding_service)
        movement_config_service = DefaultMovementConfigService()
        time_provider = InMemoryGameTimeProvider(initial_tick=100)

        spot_repo.save(Spot(SpotId(1), "S1", ""))
        exp_table = ExpTable(100, 1.5)
        status = PlayerStatusAggregate(
            player_id=PlayerId(1),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )
        player_status_repo.save(status)
        player_profile_repo.save(
            PlayerProfileAggregate.create(
                player_id=PlayerId(1),
                name=PlayerName("Test"),
                role=Role.CITIZEN,
            )
        )

        tiles = {
            Coordinate(x, y, 0): Tile(Coordinate(x, y, 0), TerrainType.grass())
            for x in range(5)
            for y in range(5)
        }
        from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
            PhysicalMapAggregate,
        )

        phys_map = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[
                WorldObject(
                    object_id=WorldObjectId.create(1),
                    coordinate=Coordinate(0, 0, 0),
                    object_type=ObjectTypeEnum.PLAYER,
                    component=ActorComponent(
                        direction=DirectionEnum.SOUTH,
                        player_id=PlayerId(1),
                    ),
                )
            ],
            gateways=[],
        )
        physical_map_repo.save(phys_map)

        service = create_movement_application_service(
            player_status_repository=player_status_repo,
            player_profile_repository=player_profile_repo,
            physical_map_repository=physical_map_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
            global_pathfinding_service=global_pathfinding_service,
            movement_config_service=movement_config_service,
            time_provider=time_provider,
            unit_of_work=unit_of_work,
        )

        result = service.move_tile(MoveTileCommand(player_id=1, direction=DirectionEnum.SOUTH))

        assert result.success is True
        assert result.to_coordinate == {"x": 0, "y": 1, "z": 0}
