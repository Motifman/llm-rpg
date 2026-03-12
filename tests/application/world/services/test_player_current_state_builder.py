"""PlayerCurrentStateBuilder のテスト。"""

from unittest.mock import MagicMock, patch

import pytest

from ai_rpg_world.domain.world.exception.map_exception import TileNotFoundException

from ai_rpg_world.application.world.contracts.dtos import (
    PlayerMovementOptionsDto,
    VisibleTileMapDto,
)
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
    HarvestableComponent,
    InteractableComponent,
)
from ai_rpg_world.domain.world.enum.world_enum import (
    DirectionEnum,
    InteractionTypeEnum,
    ObjectTypeEnum,
)
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.area import PointArea
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
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


def _make_map(
    spot_id: int,
    objects: list[WorldObject],
    location_areas: list[LocationArea] | None = None,
) -> PhysicalMapAggregate:
    tiles = {}
    for x in range(4):
        for y in range(4):
            coord = Coordinate(x, y, 0)
            tiles[coord] = Tile(coord, TerrainType.grass())
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects,
        location_areas=location_areas or [],
    )


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
        assert any(obj.object_id == 200 for obj in result.actionable_objects)
        assert any(obj.object_id == 200 for obj in result.notable_objects)
        assert chest_obj.can_store_in_chest is True
        assert chest_obj.can_take_from_chest is True
        assert chest_obj.is_notable is True
        assert npc_obj.can_interact is False
        assert npc_obj.is_notable is True

    def test_build_player_current_state_includes_active_harvest(self, setup_builder):
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.EAST, player_id=PlayerId(1)),
        )
        actor.set_busy(InMemoryGameTimeProvider(initial_tick=10).get_current_tick().add_duration(5))
        resource = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            component=HarvestableComponent(loot_table_id=1, harvest_duration=5, stamina_cost=1),
        )
        resource.component.start_harvest(WorldObjectId(1), InMemoryGameTimeProvider(initial_tick=10).get_current_tick())
        physical_map = _make_map(1, [actor, resource])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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

        assert result.active_harvest is not None
        assert result.active_harvest.target_world_object_id == 200
        assert result.active_harvest.target_display_name
        assert result.active_harvest.finish_tick == 15

    def test_build_player_current_state_with_location_area_includes_description(
        self, setup_builder
    ):
        """LocationArea 内にいる場合、current_location_description が設定される"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        location_area = LocationArea(
            location_id=LocationAreaId(1),
            area=PointArea(Coordinate(0, 0, 0)),
            name="町の広場",
            description="賑やかな市場が並ぶ中央広場。",
        )
        physical_map = _make_map(1, [actor], location_areas=[location_area])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.area_name == "町の広場"
        assert result.current_location_description == "賑やかな市場が並ぶ中央広場。"

    def test_build_player_current_state_tile_not_found_sets_terrain_type_none(
        self, setup_builder
    ):
        """get_tile が TileNotFoundException のとき current_terrain_type は None"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map(1, [actor])
        with patch.object(
            physical_map,
            "get_tile",
            side_effect=TileNotFoundException("Tile not found"),
        ):
            result = builder.build_player_current_state(
                query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.current_terrain_type is None
        assert result.player_name == "Alice"
        assert result.current_spot_name == "Town"

    def test_build_player_current_state_without_location_area_has_none_description(
        self, setup_builder
    ):
        """LocationArea がないマップでは current_location_description が None"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map(1, [actor])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.area_name is None
        assert result.current_location_description is None

    def test_build_player_current_state_includes_available_location_areas(
        self, setup_builder
    ):
        """LocationArea があるマップでは available_location_areas が is_active なもののみ含まれる"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        loc_active = LocationArea(
            location_id=LocationAreaId(10),
            area=PointArea(Coordinate(1, 1, 0)),
            name="広場",
            description="",
            is_active=True,
        )
        loc_inactive = LocationArea(
            location_id=LocationAreaId(20),
            area=PointArea(Coordinate(2, 2, 0)),
            name="非公開エリア",
            description="",
            is_active=False,
        )
        physical_map = _make_map(1, [actor], location_areas=[loc_active, loc_inactive])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.available_location_areas is not None
        assert len(result.available_location_areas) == 1
        assert result.available_location_areas[0].location_area_id == 10
        assert result.available_location_areas[0].name == "広場"

    def test_build_player_current_state_available_location_areas_empty_when_none(
        self, setup_builder
    ):
        """LocationArea がないマップでは available_location_areas が None"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map(1, [actor])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.available_location_areas is None

    def test_build_player_current_state_available_location_areas_empty_list_when_all_inactive(
        self, setup_builder
    ):
        """全て is_active=False の LocationArea のとき available_location_areas は None"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        loc_inactive = LocationArea(
            location_id=LocationAreaId(10),
            area=PointArea(Coordinate(1, 1, 0)),
            name="非公開",
            description="",
            is_active=False,
        )
        physical_map = _make_map(1, [actor], location_areas=[loc_inactive])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.available_location_areas is None

    def test_build_player_current_state_include_tile_map_true_sets_visible_tile_map(
        self, setup_builder
    ):
        """include_tile_map=True のとき visible_tile_map が設定される"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map(1, [actor])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1, include_tile_map=True),
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
        assert result.visible_tile_map is not None
        assert isinstance(result.visible_tile_map, VisibleTileMapDto)
        assert result.visible_tile_map.center_x == 0
        assert result.visible_tile_map.center_y == 0
        assert len(result.visible_tile_map.rows) > 0
        assert "草" in result.visible_tile_map.legend.get(".", "")

    def test_build_player_current_state_include_tile_map_false_omits_visible_tile_map(
        self, setup_builder
    ):
        """include_tile_map=False のとき visible_tile_map が None"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map(1, [actor])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1, include_tile_map=False),
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
        assert result.visible_tile_map is None

    def test_build_player_current_state_raises_value_error_when_current_coordinate_is_none(
        self, setup_builder
    ):
        """current_coordinate が None のとき ValueError が発生する"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        object.__setattr__(status, "_current_coordinate", None)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        physical_map = _make_map(1, [actor])

        with pytest.raises(ValueError, match="player_status.current_coordinate must not be None"):
            builder.build_player_current_state(
                query=GetPlayerCurrentStateQuery(player_id=1),
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

    def test_build_player_current_state_when_actor_not_in_map_sets_is_busy_false(
        self, setup_builder
    ):
        """物理マップにプレイヤーアクターが存在しないとき is_busy=False, busy_until_tick=None"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        # プレイヤーアクターなしのマップ（地形のみ）
        physical_map = _make_map(1, [])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.is_busy is False
        assert result.busy_until_tick is None

    def test_build_player_current_state_overlapping_location_areas_sets_area_ids(
        self, setup_builder
    ):
        """同一座標が複数の LocationArea に含まれる場合、area_ids と area_names に複数設定される"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        # 同一座標 (0,0) を含む2つの LocationArea（重なり）
        loc1 = LocationArea(
            location_id=LocationAreaId(10),
            area=PointArea(Coordinate(0, 0, 0)),
            name="広場",
            description="",
        )
        loc2 = LocationArea(
            location_id=LocationAreaId(20),
            area=PointArea(Coordinate(0, 0, 0)),
            name="市場",
            description="",
        )
        physical_map = _make_map(1, [actor], location_areas=[loc1, loc2])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert len(result.area_ids) == 2
        assert 10 in result.area_ids
        assert 20 in result.area_ids
        assert len(result.area_names) == 2
        assert "広場" in result.area_names
        assert "市場" in result.area_names
        assert result.area_id in (10, 20)
        assert result.area_name in ("広場", "市場")

    def test_build_player_current_state_single_location_area_sets_single_area_id(
        self, setup_builder
    ):
        """単一の LocationArea の場合、area_ids が1件となる（従来動作の確認）"""
        builder, status_repo, profile_repo, phys_repo, spot_repo = setup_builder
        profile_repo.save(_make_profile(1, "Alice"))
        status = _make_status(1, 1, 0, 0)
        status_repo.save(status)
        actor = WorldObject(
            object_id=WorldObjectId.create(1),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(1)),
        )
        loc = LocationArea(
            location_id=LocationAreaId(10),
            area=PointArea(Coordinate(0, 0, 0)),
            name="広場",
            description="",
        )
        physical_map = _make_map(1, [actor], location_areas=[loc])
        result = builder.build_player_current_state(
            query=GetPlayerCurrentStateQuery(player_id=1),
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
        assert result.area_ids == [10]
        assert result.area_names == ["広場"]
        assert result.area_id == 10
        assert result.area_name == "広場"

