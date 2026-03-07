"""PlayerCurrentStateBuilder のテスト。"""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.world.contracts.dtos import PlayerMovementOptionsDto
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.application.world.services.player_current_state_builder import (
    PlayerCurrentStateBuilder,
)
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel, Role
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import (
    StatGrowthFactor,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    ChestComponent,
    InteractableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import (
    DirectionEnum,
    InteractionTypeEnum,
    ObjectTypeEnum,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
    InMemorySpotRepository,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


def _make_status(player_id: int, spot_id: int = 1, x: int = 0, y: int = 0) -> PlayerStatusAggregate:
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
    )


def _make_profile(player_id: int, name: str = "Alice") -> PlayerProfileAggregate:
    return PlayerProfileAggregate.create(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=Role.CITIZEN,
    )


def _make_map(spot_id: int, objects: list[WorldObject]) -> PhysicalMapAggregate:
    tiles = {}
    for x in range(4):
        for y in range(4):
            coord = Coordinate(x, y, 0)
            tiles[coord] = Tile(coord, TerrainType.grass())
    return PhysicalMapAggregate(spot_id=SpotId(spot_id), tiles=tiles, objects=objects)


class TestPlayerCurrentStateBuilder:
    @pytest.fixture
    def setup_builder(self):
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Town", "A town"))
        spot_repo.save(Spot(SpotId(2), "Field", "A field"))
        builder = PlayerCurrentStateBuilder(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            spot_repository=spot_repo,
            connected_spots_provider=GatewayBasedConnectedSpotsProvider(phys_repo),
            game_time_provider=InMemoryGameTimeProvider(initial_tick=10),
        )
        return builder, status_repo, profile_repo, phys_repo, spot_repo

    def test_build_visible_context_filters_by_los(self, setup_builder):
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        player = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        hidden = WorldObject(
            object_id=WorldObjectId.create(2),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(2)),
        )
        wall_map = _make_map(1, [player, hidden])
        wall_map.change_tile_terrain(Coordinate(1, 0, 0), TerrainType.wall())
        result = builder.build_visible_context(
            player_id=1,
            player_name="Alice",
            spot=spot_repo.find_by_id(SpotId(1)),
            physical_map=wall_map,
            origin=Coordinate(0, 0, 0),
            view_distance=3,
        )
        assert [obj.player_id_value for obj in result.visible_objects if obj.player_id_value] == [1]

    def test_build_player_current_state_populates_runtime_relevant_flags(self, setup_builder):
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status.set_destination(
            Coordinate(2, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0), Coordinate(2, 0, 0)],
        )
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.EAST, player_id=PlayerId(1)),
        )
        actor.set_busy(InMemoryGameTimeProvider(initial_tick=10).get_current_tick().add_duration(5))
        chest = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            is_blocking=False,
            component=ChestComponent(is_open=True, item_ids=[]),
        )
        npc = WorldObject(
            object_id=WorldObjectId(201),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=InteractableComponent(InteractionTypeEnum.TALK),
        )
        physical_map = _make_map(1, [actor, chest, npc])
        query = GetPlayerCurrentStateQuery(player_id=1)
        result = builder.build_player_current_state(
            query=query,
            player_status=status,
            player_name="Alice",
            spot=spot_repo.find_by_id(SpotId(1)),
            physical_map=physical_map,
            available_moves_result=PlayerMovementOptionsDto(
                player_id=1,
                player_name="Alice",
                current_spot_id=1,
                current_spot_name="Town",
                available_moves=[],
                total_available_moves=0,
            ),
        )
        chest_obj = next(obj for obj in result.visible_objects if obj.object_id == 200)
        npc_obj = next(obj for obj in result.visible_objects if obj.object_id == 201)
        assert result.is_busy is True
        assert result.busy_until_tick == 15
        assert result.has_active_path is True
        assert chest_obj.can_store_in_chest is True
        assert chest_obj.can_take_from_chest is True
        assert npc_obj.can_interact is False

