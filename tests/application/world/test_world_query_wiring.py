"""World query wiring（create_world_query_service）のテスト。"""

import pytest

from ai_rpg_world.application.world.world_query_wiring import create_world_query_service
from ai_rpg_world.application.world.contracts.queries import (
    GetPlayerLocationQuery,
    GetSpotContextForPlayerQuery,
    GetAvailableMovesQuery,
)
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
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
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
    InMemorySpotRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
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


class TestCreateWorldQueryService:
    """create_world_query_service で構築したサービスが正常に動作することを検証する。"""

    def test_create_world_query_service_produces_working_service(self):
        """create_world_query_service が動作する WorldQueryService を返すこと"""
        data_store = InMemoryDataStore()
        data_store.clear_all()

        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Default Spot", ""))
        connected_spots_provider = GatewayBasedConnectedSpotsProvider(phys_repo)

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
            navigation_state=PlayerNavigationState.from_parts(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(0, 0, 0),
            ),
        )
        status_repo.save(status)
        profile_repo.save(
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
        )
        phys_repo.save(phys_map)

        service = create_world_query_service(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
        )

        loc = service.get_player_location(GetPlayerLocationQuery(player_id=1))
        assert loc is not None
        assert loc.player_id == 1
        assert loc.player_name == "Test"

    def test_get_spot_context_returns_none_when_player_not_placed(self):
        """プレイヤーが未配置の場合、get_spot_context_for_player は None を返すこと"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Default", ""))
        profile_repo.save(
            PlayerProfileAggregate.create(
                player_id=PlayerId(1),
                name=PlayerName("Test"),
                role=Role.CITIZEN,
            )
        )

        service = create_world_query_service(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=GatewayBasedConnectedSpotsProvider(phys_repo),
        )

        result = service.get_spot_context_for_player(
            GetSpotContextForPlayerQuery(player_id=1)
        )
        assert result is None
