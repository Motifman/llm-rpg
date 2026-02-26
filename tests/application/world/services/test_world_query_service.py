"""WorldQueryService のテスト。正常・例外を網羅する。"""

import pytest
from typing import List, Dict
from unittest.mock import patch

from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world.contracts.queries import GetPlayerLocationQuery
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.application.world.exceptions.base_exception import WorldSystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
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
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import InMemoryPlayerProfileRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


class TestWorldQueryService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()

        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Default Spot", ""))

        service = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )
        return service, status_repo, profile_repo, phys_repo, spot_repo

    def _create_sample_status(self, player_id: int, spot_id: int = 1, x: int = 0, y: int = 0):
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

    def _create_sample_profile(self, player_id: int, name: str = "TestPlayer"):
        return PlayerProfileAggregate.create(
            player_id=PlayerId(player_id),
            name=PlayerName(name),
            role=Role.CITIZEN,
        )

    def _create_sample_map(self, spot_id: int, width: int = 10, height: int = 10, objects: List = None):
        tiles = {}
        for x in range(width):
            for y in range(height):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        return PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=objects or [],
        )

    def _create_player_object(self, player_id: int, x: int = 0, y: int = 0):
        return WorldObject(
            object_id=WorldObjectId.create(player_id),
            coordinate=Coordinate(x, y, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH, player_id=PlayerId(player_id)),
        )

    # --- 正常ケース ---

    def test_get_player_location_returns_dto_when_placed(self, setup_service):
        """配置済みプレイヤーの位置が DTO で返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 3, 4))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 3, 4)]))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Alice"
        assert result.current_spot_id == spot_id
        assert result.x == 3
        assert result.y == 4
        assert result.z == 0

    def test_get_player_location_returns_none_when_not_placed(self, setup_service):
        """未配置の場合は None を返すこと"""
        service, status_repo, profile_repo, _, spot_repo = setup_service
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status._current_coordinate = None
        status_repo.save(status)

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is None

    def test_get_player_location_returns_none_when_player_not_in_repo(self, setup_service):
        """プレイヤーがリポジトリに存在しない場合は None を返すこと"""
        service, _, _, _, _ = setup_service

        result = service.get_player_location(GetPlayerLocationQuery(player_id=99999))

        assert result is None

    def test_get_player_location_includes_spot_name_and_description(self, setup_service):
        """スポット名・説明が DTO に含まれること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        spot_repo.save(Spot(SpotId(spot_id), "Town Square", "A central area"))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert result.current_spot_name == "Town Square"
        assert result.current_spot_description == "A central area"

    # --- 例外ケース ---

    def test_get_player_location_raises_player_not_found_when_profile_missing(self, setup_service):
        """プロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, status_repo, _, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException) as exc_info:
            service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert exc_info.value.context.get("player_id") == player_id

    def test_get_player_location_raises_map_not_found_when_spot_missing(self, setup_service):
        """スポットが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 999
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with pytest.raises(MapNotFoundException) as exc_info:
            service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert exc_info.value.context.get("spot_id") == spot_id

    def test_get_player_location_raises_world_system_error_on_unexpected_exception(self, setup_service):
        """想定外の例外時に WorldSystemErrorException が発生すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo = setup_service
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))

        with patch.object(spot_repo, "find_by_id", side_effect=RuntimeError("unexpected")):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.get_player_location(GetPlayerLocationQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None
            assert isinstance(exc_info.value.original_exception, RuntimeError)


class TestGetPlayerLocationQueryValidation:
    """GetPlayerLocationQuery のバリデーション"""

    def test_query_raises_value_error_for_invalid_player_id_zero(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerLocationQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self):
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerLocationQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self):
        q = GetPlayerLocationQuery(player_id=1)
        assert q.player_id == 1
