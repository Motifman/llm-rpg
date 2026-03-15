"""VisibleContextQueryService のテスト（正常・境界・例外・バリデーション）"""

import pytest
from typing import List
from unittest.mock import MagicMock

from ai_rpg_world.application.world.services.visible_context_query_service import (
    VisibleContextQueryService,
)
from ai_rpg_world.application.world.contracts.queries import GetVisibleContextQuery
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
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
        navigation_state=PlayerNavigationState.from_parts(
            current_spot_id=None if spot_id_none else SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0) if not spot_id_none else None,
        ),
    )


def _make_profile(player_id: int, name: str = "TestPlayer") -> PlayerProfileAggregate:
    """テスト用 PlayerProfileAggregate を作成"""
    return PlayerProfileAggregate.create(
        player_id=PlayerId(player_id),
        name=PlayerName(name),
        role=Role.CITIZEN,
    )


def _make_map(
    spot_id: int, width: int = 10, height: int = 10, objects: List = None
) -> PhysicalMapAggregate:
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


class TestVisibleContextQueryServiceNormal:
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
        return VisibleContextQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

    def test_returns_dto_when_placed(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """配置済みプレイヤーの視界内オブジェクトが VisibleContextDto で返ること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id, "Bob"))
        status_repo.save(_make_status(player_id, spot_id, 5, 5))
        spot_repo.save(Spot(SpotId(spot_id), "Town", "A town"))
        phys_repo.save(
            _make_map(
                spot_id,
                objects=[_make_player_object(player_id, 5, 5)],
            )
        )

        result = service.get_visible_context(
            GetVisibleContextQuery(player_id=player_id, distance=3)
        )

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Bob"
        assert result.spot_id == spot_id
        assert result.center_x == 5
        assert result.center_y == 5
        assert result.view_distance == 3
        assert isinstance(result.visible_objects, list)
        assert len(result.visible_objects) >= 1
        obj = result.visible_objects[0]
        assert obj.object_type == "PLAYER"
        assert obj.distance >= 0
        assert obj.display_name == "Bob"
        assert obj.object_kind == "player"
        assert obj.direction_from_player == "ここ"
        assert obj.player_id_value == 1
        assert obj.is_self is True

    def test_returns_dto_with_default_distance(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """distance 省略時はデフォルト 5 で返ること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Default", ""))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id)]))

        result = service.get_visible_context(GetVisibleContextQuery(player_id=player_id))

        assert result is not None
        assert result.view_distance == 5


class TestVisibleContextQueryServiceBoundary:
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
        return VisibleContextQueryService(
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

        result = service.get_visible_context(
            GetVisibleContextQuery(player_id=player_id)
        )

        assert result is None

    def test_returns_none_when_player_not_in_repo(self, service, spot_repo):
        """プレイヤーがリポジトリに存在しない場合は None を返すこと"""
        spot_repo.save(Spot(SpotId(1), "Default", ""))

        result = service.get_visible_context(
            GetVisibleContextQuery(player_id=99999)
        )

        assert result is None

    def test_distance_zero_returns_center_only(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """distance=0 のとき視界内は自身のみ（または空）となること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 1, 1))
        spot_repo.save(Spot(SpotId(spot_id), "Default", ""))
        phys_repo.save(
            _make_map(spot_id, objects=[_make_player_object(player_id, 1, 1)])
        )

        result = service.get_visible_context(
            GetVisibleContextQuery(player_id=player_id, distance=0)
        )

        assert result is not None
        assert result.view_distance == 0
        assert len(result.visible_objects) >= 1

    def test_filters_by_los_excludes_object_behind_wall(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """遮蔽物（壁）の向こうにいる対象は visible_objects に含まれないこと"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Default", ""))

        tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall()),
            Coordinate(2, 0, 0): Tile(Coordinate(2, 0, 0), TerrainType.grass()),
        }
        hidden_player = _make_player_object(2, 2, 0)
        phys_repo.save(
            PhysicalMapAggregate(
                spot_id=SpotId(spot_id),
                tiles=tiles,
                objects=[
                    _make_player_object(player_id, 0, 0),
                    hidden_player,
                ],
            )
        )

        result = service.get_visible_context(
            GetVisibleContextQuery(player_id=player_id, distance=3)
        )

        assert result is not None
        assert {obj.player_id_value for obj in result.visible_objects if obj.player_id_value is not None} == {1}


class TestVisibleContextQueryServiceExceptions:
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
        return VisibleContextQueryService(
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
            service.get_visible_context(
                GetVisibleContextQuery(player_id=player_id)
            )

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
        phys_repo.save(
            _make_map(spot_id, objects=[_make_player_object(player_id)])
        )

        with pytest.raises(MapNotFoundException) as exc_info:
            service.get_visible_context(
                GetVisibleContextQuery(player_id=player_id)
            )

        assert exc_info.value.context.get("spot_id") == spot_id

    def test_raises_map_not_found_when_physical_map_missing(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """PhysicalMap が存在しない場合に MapNotFoundException を送出すること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Spot", ""))
        # phys_repo にマップを保存しない（spot のみ）

        with pytest.raises(MapNotFoundException) as exc_info:
            service.get_visible_context(
                GetVisibleContextQuery(player_id=player_id)
            )

        assert exc_info.value.context.get("spot_id") == spot_id

    def test_propagates_find_by_id_exception(self):
        """find_by_id が例外を投げた場合、その例外を伝播すること"""
        status_repo = MagicMock()
        status_repo.find_by_id.side_effect = RuntimeError("find_by_id failed")
        profile_repo = MagicMock()
        phys_repo = MagicMock()
        spot_repo = MagicMock()

        service = VisibleContextQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

        with pytest.raises(RuntimeError, match="find_by_id failed"):
            service.get_visible_context(
                GetVisibleContextQuery(player_id=1)
            )

    def test_propagates_build_visible_context_exception(self):
        """VisibleObjectReadModelBuilder が例外を投げた場合、その例外を伝播すること"""
        data_store = InMemoryDataStore()
        status_repo = InMemoryPlayerStatusRepository(data_store)
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Spot", ""))

        status_repo.save(_make_status(1, 1, 0, 0))
        profile_repo.save(_make_profile(1))

        phys_repo = MagicMock()
        phys_repo.find_by_spot_id.side_effect = ValueError("map error")

        service = VisibleContextQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
        )

        with pytest.raises(ValueError, match="map error"):
            service.get_visible_context(
                GetVisibleContextQuery(player_id=1)
            )


class TestGetVisibleContextQueryValidation:
    """GetVisibleContextQuery のバリデーション"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def service(self, data_store):
        return VisibleContextQueryService(
            player_status_repository=InMemoryPlayerStatusRepository(data_store),
            player_profile_repository=InMemoryPlayerProfileRepository(data_store),
            physical_map_repository=InMemoryPhysicalMapRepository(data_store),
            spot_repository=InMemorySpotRepository(data_store),
        )

    def test_query_raises_value_error_for_invalid_player_id_zero(self, service):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetVisibleContextQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self, service):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetVisibleContextQuery(player_id=-1)

    def test_query_raises_value_error_for_negative_distance(self, service):
        """distance が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="distance must be 0 or greater"):
            GetVisibleContextQuery(player_id=1, distance=-1)

    def test_query_accepts_positive_player_id_and_default_distance(self, service):
        """player_id が正の場合、Query は正常に作成でき、distance はデフォルト 5 となること"""
        query = GetVisibleContextQuery(player_id=1)
        assert query.player_id == 1
        assert query.distance == 5

    def test_query_accepts_custom_distance(self, service):
        """distance を指定した場合、その値が使用されること"""
        query = GetVisibleContextQuery(player_id=1, distance=10)
        assert query.player_id == 1
        assert query.distance == 10
