"""AvailableMovesQueryService のテスト（正常・境界・例外・遷移条件・バリデーション）"""

import pytest
from typing import List
from unittest.mock import MagicMock

from ai_rpg_world.application.world.services.available_moves_query_service import (
    AvailableMovesQueryService,
)
from ai_rpg_world.application.world.contracts.queries import GetAvailableMovesQuery
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
)
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
)
from ai_rpg_world.domain.world.value_object.transition_condition import RequireToll
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
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import RectArea
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
from ai_rpg_world.infrastructure.repository.in_memory_transition_policy_repository import (
    InMemoryTransitionPolicyRepository,
)
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
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


class TestAvailableMovesQueryServiceNormal:
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
    def connected_spots_provider(self, phys_repo):
        return GatewayBasedConnectedSpotsProvider(phys_repo)

    @pytest.fixture
    def service(
        self,
        status_repo,
        profile_repo,
        phys_repo,
        spot_repo,
        connected_spots_provider,
    ):
        return AvailableMovesQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
        )

    def test_returns_dto_when_placed(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """配置済みプレイヤーの利用可能な移動先が PlayerMovementOptionsDto で返ること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id, "Charlie"))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Town", ""))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id)]))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

        assert result is not None
        assert result.player_id == player_id
        assert result.player_name == "Charlie"
        assert result.current_spot_id == spot_id
        assert isinstance(result.available_moves, list)
        assert result.total_available_moves == len(result.available_moves)
        for move in result.available_moves:
            assert move.conditions_met is True
            assert move.failed_conditions == []

    def test_includes_connected_spot_when_gateway_exists(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """ゲートウェイで接続されたスポットが available_moves に含まれること"""
        spot_repo.save(Spot(SpotId(1), "Here", ""))
        spot_repo.save(Spot(SpotId(2), "There", ""))
        gateway = Gateway(
            GatewayId(1),
            "GateToThere",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[_make_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        phys_repo.save(_make_map(2))
        profile_repo.save(_make_profile(1))
        status_repo.save(_make_status(1, 1, 0, 0))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=1))

        assert result is not None
        assert result.total_available_moves >= 1
        spot_ids = [m.spot_id for m in result.available_moves]
        assert 2 in spot_ids
        move_to_2 = next(m for m in result.available_moves if m.spot_id == 2)
        assert move_to_2.spot_name == "There"
        assert move_to_2.conditions_met is True


class TestAvailableMovesQueryServiceWithoutTransitionPolicy:
    """遷移ポリシーなし（conditions_met は常に True）"""

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
    def connected_spots_provider(self, phys_repo):
        return GatewayBasedConnectedSpotsProvider(phys_repo)

    @pytest.fixture
    def service(
        self,
        status_repo,
        profile_repo,
        phys_repo,
        spot_repo,
        connected_spots_provider,
    ):
        return AvailableMovesQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
            transition_policy_repository=None,
            transition_condition_evaluator=None,
        )

    def test_conditions_met_true_when_no_transition_policy(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """遷移ポリシー・評価器が None の場合、すべて conditions_met=True で返ること"""
        spot_repo.save(Spot(SpotId(1), "Here", ""))
        spot_repo.save(Spot(SpotId(2), "There", ""))
        gateway = Gateway(
            GatewayId(1),
            "Gate",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[_make_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        phys_repo.save(_make_map(2))
        profile_repo.save(_make_profile(1))
        status_repo.save(_make_status(1, 1, 0, 0))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=1))

        assert result is not None
        for move in result.available_moves:
            assert move.conditions_met is True
            assert move.failed_conditions == []


class TestAvailableMovesQueryServiceWithTransitionPolicy:
    """遷移条件あり"""

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
    def policy_repo(self):
        return InMemoryTransitionPolicyRepository()

    @pytest.fixture
    def evaluator(self):
        return TransitionConditionEvaluator()

    @pytest.fixture
    def connected_spots_provider(self, phys_repo):
        return GatewayBasedConnectedSpotsProvider(phys_repo)

    @pytest.fixture
    def service(
        self,
        status_repo,
        profile_repo,
        phys_repo,
        spot_repo,
        connected_spots_provider,
        policy_repo,
        evaluator,
    ):
        return AvailableMovesQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
            transition_policy_repository=policy_repo,
            transition_condition_evaluator=evaluator,
        )

    def test_conditions_met_false_when_require_toll_not_met(
        self, service, status_repo, profile_repo, phys_repo, spot_repo, policy_repo
    ):
        """RequireToll 条件があり所持金が不足の場合、conditions_met=False となること"""
        spot_repo.save(Spot(SpotId(1), "Here", ""))
        spot_repo.save(Spot(SpotId(2), "There", ""))
        gateway = Gateway(
            GatewayId(1),
            "Gate",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[_make_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        phys_repo.save(_make_map(2))
        profile_repo.save(_make_profile(1))
        status_repo.save(_make_status(1, 1, 0, 0))
        policy_repo.set_conditions(SpotId(1), SpotId(2), [RequireToll(amount_gold=5000)])

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=1))

        assert result is not None
        move_to_2 = next(m for m in result.available_moves if m.spot_id == 2)
        assert move_to_2.conditions_met is False
        assert len(move_to_2.failed_conditions) >= 1

    def test_conditions_met_true_when_require_toll_met(
        self, service, status_repo, profile_repo, phys_repo, spot_repo, policy_repo
    ):
        """RequireToll 条件があり所持金が足りる場合、conditions_met=True となること"""
        spot_repo.save(Spot(SpotId(1), "Here", ""))
        spot_repo.save(Spot(SpotId(2), "There", ""))
        gateway = Gateway(
            GatewayId(1),
            "Gate",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[_make_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        phys_repo.save(_make_map(2))
        profile_repo.save(_make_profile(1))
        status_repo.save(_make_status(1, 1, 0, 0))
        policy_repo.set_conditions(SpotId(1), SpotId(2), [RequireToll(amount_gold=100)])

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=1))

        assert result is not None
        move_to_2 = next(m for m in result.available_moves if m.spot_id == 2)
        assert move_to_2.conditions_met is True
        assert move_to_2.failed_conditions == []


class TestAvailableMovesQueryServiceBoundary:
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
    def connected_spots_provider(self, phys_repo):
        return GatewayBasedConnectedSpotsProvider(phys_repo)

    @pytest.fixture
    def service(
        self,
        status_repo,
        profile_repo,
        phys_repo,
        spot_repo,
        connected_spots_provider,
    ):
        return AvailableMovesQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
        )

    def test_returns_none_when_not_placed(
        self, service, status_repo, profile_repo, spot_repo
    ):
        """未配置の場合は None を返すこと"""
        player_id = 1
        profile_repo.save(_make_profile(player_id))
        status = _make_status(player_id, spot_id_none=True)
        status_repo.save(status)
        spot_repo.save(Spot(SpotId(1), "Default", ""))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

        assert result is None

    def test_returns_none_when_player_not_in_repo(self, service, spot_repo):
        """プレイヤーがリポジトリに存在しない場合は None を返すこと"""
        spot_repo.save(Spot(SpotId(1), "Default", ""))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=99999))

        assert result is None

    def test_returns_empty_available_moves_when_no_connections(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """接続スポットがない場合、available_moves が空、total_available_moves が 0 であること"""
        player_id = 1
        spot_id = 1
        profile_repo.save(_make_profile(player_id))
        status_repo.save(_make_status(player_id, spot_id, 0, 0))
        spot_repo.save(Spot(SpotId(spot_id), "Isolated", ""))
        phys_repo.save(_make_map(spot_id, objects=[_make_player_object(player_id)]))

        result = service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

        assert result is not None
        assert result.available_moves == []
        assert result.total_available_moves == 0


class TestAvailableMovesQueryServiceExceptions:
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
    def connected_spots_provider(self, phys_repo):
        return GatewayBasedConnectedSpotsProvider(phys_repo)

    @pytest.fixture
    def service(
        self,
        status_repo,
        profile_repo,
        phys_repo,
        spot_repo,
        connected_spots_provider,
    ):
        return AvailableMovesQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
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
            service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

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
            service.get_available_moves(GetAvailableMovesQuery(player_id=player_id))

        assert exc_info.value.context.get("spot_id") == spot_id

    def test_propagates_find_by_id_exception(self):
        """find_by_id が例外を投げた場合、その例外を伝播すること"""
        status_repo = MagicMock()
        status_repo.find_by_id.side_effect = RuntimeError("find_by_id failed")
        profile_repo = MagicMock()
        phys_repo = MagicMock()
        spot_repo = MagicMock()
        connected_spots_provider = MagicMock()

        service = AvailableMovesQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
        )

        with pytest.raises(RuntimeError, match="find_by_id failed"):
            service.get_available_moves(GetAvailableMovesQuery(player_id=1))

    def test_raises_map_not_found_when_connected_spot_does_not_exist(
        self, service, status_repo, profile_repo, phys_repo, spot_repo
    ):
        """接続先スポットが spot_repository に存在しない場合、MapNotFoundException を送出すること（データ不整合）"""
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
        from ai_rpg_world.domain.world.value_object.area import RectArea

        spot_repo.save(Spot(SpotId(1), "Here", ""))
        # spot_id=2 は spot_repo に保存しない（ゲートウェイは spot 2 を指す）
        gateway = Gateway(
            GatewayId(1),
            "Gate",
            RectArea(min_x=5, max_x=6, min_y=5, max_y=6, min_z=0, max_z=0),
            SpotId(2),
            Coordinate(0, 0, 0),
        )
        tiles = {}
        for x in range(10):
            for y in range(10):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, TerrainType.grass())
        map1 = PhysicalMapAggregate(
            spot_id=SpotId(1),
            tiles=tiles,
            objects=[_make_player_object(1, 0, 0)],
            gateways=[gateway],
        )
        phys_repo.save(map1)
        profile_repo.save(_make_profile(1))
        status_repo.save(_make_status(1, 1, 0, 0))

        with pytest.raises(MapNotFoundException) as exc_info:
            service.get_available_moves(GetAvailableMovesQuery(player_id=1))

        assert exc_info.value.context.get("spot_id") == 2


class TestGetAvailableMovesQueryValidation:
    """GetAvailableMovesQuery のバリデーション"""

    @pytest.fixture
    def data_store(self):
        return InMemoryDataStore()

    @pytest.fixture
    def service(self, data_store):
        return AvailableMovesQueryService(
            player_status_repository=InMemoryPlayerStatusRepository(data_store),
            player_profile_repository=InMemoryPlayerProfileRepository(data_store),
            physical_map_repository=InMemoryPhysicalMapRepository(data_store),
            spot_repository=InMemorySpotRepository(data_store),
            connected_spots_provider=GatewayBasedConnectedSpotsProvider(
                InMemoryPhysicalMapRepository(data_store)
            ),
        )

    def test_query_raises_value_error_for_invalid_player_id_zero(self, service):
        """player_id が 0 の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetAvailableMovesQuery(player_id=0)

    def test_query_raises_value_error_for_negative_player_id(self, service):
        """player_id が負の場合、Query の __post_init__ で ValueError が発生すること"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            GetAvailableMovesQuery(player_id=-1)

    def test_query_accepts_positive_player_id(self, service):
        """player_id が正の場合、Query は正常に作成できること"""
        query = GetAvailableMovesQuery(player_id=1)
        assert query.player_id == 1
