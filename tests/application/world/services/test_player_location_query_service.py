"""PlayerLocationQueryService のテスト（正常・境界・例外）"""

import pytest
from typing import List
from unittest.mock import MagicMock

from ai_rpg_world.application.world.services.player_location_query_service import (
    PlayerLocationQueryService,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerLocationQuery
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
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
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
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


def _make_status(
    player_id: int,
    spot_id: int = 1,
    x: int = 0,
    y: int = 0,
    spot_id_none: bool = False,
) -> PlayerStatusAggregate:
    """テスト用 PlayerStatusAggregate を作成"""
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
        current_spot_id=None if spot_id_none else SpotId(spot_id),
        current_coordinate=Coordinate(x, y, 0) if not spot_id_none else None,
    )


def _make_profile(player_id: int, name: str = "TestPlayer") -> PlayerProfileAggregate:
    """テスト用 PlayerProfileAggregate を作成"""
    return PlayerProfileAggregate.create(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=Role.CITIZEN,
    )


def _make_map(spot_id: int, width: int = 10, height: int = 10, objects: List = None) -> PhysicalMapAggregate:
    """テスト用 PhysicalMapAggregate を作成"""
    tiles = {}
    for xi in range(width):
        for yi in range(height):
            coord = Coordinate(xi, yi, 0)
            tiles[coord] = Tile(coord, TerrainType.grass())
    return PhysicalMapAggregate(
        spot_id=SpotId(spot_id),
        tiles=tiles,
        objects=objects or [],
    )


def _make_player_object(player_id: int, x: int = 0, y: int = 0) -> WorldObject:
    """テスト用プレイヤー WorldObject を作成"""
    return WorldObject(
        object_id=WorldObjectId.create(player_id),
        coordinate=Coordinate(x, y, 0),
        object_type=ObjectTypeEnum.PLAYER,
        component=ActorComponent(
            direction=DirectionEnum.SOUTH,
            player_id=PlayerId(player_id),
        ),
    )


class TestPlayerLocationQueryServiceNormal:
    """正常ケース"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store)

    @pytest.fixture
    def profile_repo(self, data_store):
        return InMemoryPlayerProfileRepository(data_store)

    @pytest.fixture
    def phys_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store)

    @pytest.fixture
    def spot_repo(self, data_store):
        return InMemorySpotRepository(data_store)

    @pytest.fixture
    def service(self, status_repo, profile_repo, phys_repo, spot_repo):
        return PlayerLocationQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

    def test_returns_dto_when_placed(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """配置済みプレイヤーの位置が DTO で返ること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id, "Alice"))
        status_repo.save(_make_status(player_id, spot_id, 3, 4))
        spot_repo.save(Spot(SpotId(spot_id), "Town", "A town"))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id, 3, 4)]))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Alice"
        assert result.current_spot_id == spot_id
        assert result.current_spot_name == "Town"
        assert result.current_spot_description == "A town"
        assert result.x == 3
        assert result.y == 4
        assert result.z == 0

    def test_includes_area_ids_and_names_when_in_location_area(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """ロケーションエリア内にいる場合、area_ids と area_names が含まれること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Spot", ""))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id)]))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert isinstance(result.area_ids, list)
        assert isinstance(result.area_names, list)


class TestPlayerLocationQueryServiceBoundary:
    """境界ケース"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store)

    @pytest.fixture
    def profile_repo(self, data_store):
        return InMemoryPlayerProfileRepository(data_store)

    @pytest.fixture
    def phys_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store)

    @pytest.fixture
    def spot_repo(self, data_store):
        return InMemorySpotRepository(data_store)

    @pytest.fixture
    def service(self, status_repo, profile_repo, phys_repo, spot_repo):
        return PlayerLocationQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

    def test_returns_none_when_not_placed(
        self, service, status_repo, profile_repo, spot_repo
    ):
        """未配置（current_spot_id/current_coordinate が None）の場合は None を返すこと"""
        player_id = 1
        profile_repo.save(_make_profile(player_id))
        status = _make_status(player_id, spot_id_none=True)
        status_repo.save(status)
        spot_repo.save(Spot(SpotId(1), "Default", ""))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is None

    def test_returns_none_when_player_not_in_repo(self, service, spot_repo):
        """プレイヤーがリポジトリに存在しない場合は None を返すこと"""
        spot_repo.save(Spot(SpotId(1), "Default", ""))

        result = service.get_player_location(GetPlayerLocationQuery(player_id=99999))

        assert result is None

    def test_returns_dto_with_empty_areas_when_physical_map_missing(
        self, service, status_repo, profile_repo, spot_repo
    ):
        """PhysicalMap が存在しない場合、area_ids/area_names が空リスト、area_id/area_name が None になること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Spot", ""))
        # phys_repo にマップを保存しない（spot のみ）

        result = service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert result is not None
        assert result.area_ids == []
        assert result.area_names == []
        assert result.area_id is None
        assert result.area_name is None


class TestPlayerLocationQueryServiceExceptions:
    """例外ケース"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def status_repo(self, data_store):
        return InMemoryPlayerStatusRepository(data_store)

    @pytest.fixture
    def profile_repo(self, data_store):
        return InMemoryPlayerProfileRepository(data_store)

    @pytest.fixture
    def phys_repo(self, data_store):
        return InMemoryPhysicalMapRepository(data_store)

    @pytest.fixture
    def spot_repo(self, data_store):
        return InMemorySpotRepository(data_store)

    @pytest.fixture
    def service(self, status_repo, profile_repo, phys_repo, spot_repo):
        return PlayerLocationQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

    def test_raises_player_not_found_when_profile_missing(
        self, service, status_repo, phys_repo, spot_repo
    ):
        """プロフィールが存在しない場合に PlayerNotFoundException を送出すること"""
        player_id = 1
        spot_id = 1
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Spot", ""))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id)]))

        with pytest.raises(PlayerNotFoundException) as exc_info:
            service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert exc_info.value.context.get("player_id") == player_id

    def test_raises_map_not_found_when_spot_missing(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """スポットが存在しない場合に MapNotFoundException を送出すること"""
        player_id = 1
        spot_id = 999
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(1), "Default", ""))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id)]))

        with pytest.raises(MapNotFoundException) as exc_info:
            service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert exc_info.value.context.get("spot_id") == spot_id

    def test_propagates_find_by_id_exception(self):
        """find_by_id が例外を投げた場合、その例外を伝播すること"""
        status_repo = MagicMock()
        status_repo.find_by_id.side_effect = RuntimeError("find_by_id failed")
        profile_repo = MagicMock()
        phys_repo = MagicMock()
        spot_repo = MagicMock()

        service = PlayerLocationQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

        with pytest.raises(RuntimeError, match="find_by_id failed"):
            service.get_player_location(GetPlayerLocationQuery(player_id=1))

    def test_propagates_find_by_id_on_profile_exception(self):
        """プロフィール取得時に例外が発生した場合、その例外を伝播すること"""
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = MagicMock()
        profile_repo.find_by_id.side_effect = ValueError("profile repo error")
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Spot", ""))

        status_repo.save(_make_status(1, 1, 0, 0))
        phys_repo.save(_make_map(1, objects=[_make_player_object(1)]))

        service = PlayerLocationQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

        with pytest.raises(ValueError, match="profile repo error"):
            service.get_player_location(GetPlayerLocationQuery(player_id=1))


class TestGetPlayerLocationQueryValidation:
    """GetPlayerLocationQuery のバリデーション"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def service(self, data_store):
        return PlayerLocationQueryService(
            player_status_repository=InMemoryPlayerStatusRepository(data_store),
            player_profile_repository=InMemoryPlayerProfileRepository(data_store),
            physical_map_repository=InMemoryPhysicalMapRepository(data_store),
            spot_repository=InMemorySpotRepository(data_store),
        )

    def test_query_raises_value_error_for_invalid_player_id_zero(self, service):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerLocationQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self, service):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetPlayerLocationQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self, service):
        """player_id が正の場合、Query は正常に作成できること"""
        query = GetPlayerLocationQuery(player_id=1)
        assert query.player_id == 1
