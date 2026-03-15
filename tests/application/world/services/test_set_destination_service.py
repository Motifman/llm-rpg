"""SetDestinationService の単体テスト。正常系・例外系を網羅する。"""

import pytest
from typing import List, Dict
from unittest.mock import MagicMock, patch

from ai_rpg_world.application.world.services.set_destination_service import (
    SetDestinationService,
    SetDestinationResult,
    ReplanPathCalculationResult,
)
from ai_rpg_world.application.world.contracts.commands import SetDestinationCommand
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.exception.map_exception import (
    LocationAreaNotFoundException,
    ObjectNotFoundException,
    PathNotFoundException,
)
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
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
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
    AStarPathfindingStrategy,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork


class TestSetDestinationService:
    """SetDestinationService のテスト。"""

    @pytest.fixture
    def setup_service(self):
        """SetDestinationService とテスト用リポジトリを構築する。"""
        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_repo = InMemorySpotRepository(data_store, unit_of_work)
        connected_spots_provider = GatewayBasedConnectedSpotsProvider(physical_map_repo)
        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        global_pathfinding_service = GlobalPathfindingService(pathfinding_service)

        set_destination_service = SetDestinationService(
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            connected_spots_provider=connected_spots_provider,
            global_pathfinding_service=global_pathfinding_service,
        )

        return (
            set_destination_service,
            player_status_repo,
            physical_map_repo,
            spot_repo,
            unit_of_work,
        )

    def _create_sample_status(
        self,
        player_id: int,
        spot_id: int = 1,
        x: int = 0,
        y: int = 0,
        navigation_state: PlayerNavigationState | None = None,
    ) -> PlayerStatusAggregate:
        nav = navigation_state or PlayerNavigationState.from_parts(
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0),
        )
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
            navigation_state=nav,
        )

    def _register_spots(self, spot_repo, spots_data: List[Dict]):
        for s in spots_data:
            spot_repo.save(Spot(SpotId(s["id"]), s["name"], s.get("desc", "")))

    def _create_player_object(self, player_id: int, x: int = 0, y: int = 0) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId.create(player_id),
            coordinate=Coordinate(x, y, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(
                direction=DirectionEnum.SOUTH,
                player_id=PlayerId(player_id),
            ),
        )

    def _create_sample_map(
        self,
        spot_id: int,
        width: int = 10,
        height: int = 10,
        objects: List[WorldObject] = None,
        terrain_type: TerrainType = None,
    ) -> PhysicalMapAggregate:
        tiles = {}
        for x in range(width):
            for y in range(height):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, terrain_type or TerrainType.grass())
        return PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=objects or [],
            gateways=[],
        )

    # --- resolve_and_calculate_path 正常系 ---

    def test_resolve_and_calculate_path_spot_already_at_destination(
        self, setup_service
    ):
        """同一スポットにいるとき、already_at_destination で成功を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="spot",
                    target_spot_id=spot_id,
                )
            )

        assert result.success is True
        assert result.already_at_destination is True
        assert result.path_found is False
        assert "既に目的地のスポットにいます" in result.message
        assert result.temp_goal is None
        assert result.path is None

    def test_resolve_and_calculate_path_location_path_found(self, setup_service):
        """ロケーション指定で経路計算が成功する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        location_area = LocationArea(
            location_id=LocationAreaId(10),
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
            name="Goal",
            description="",
        )
        phys_map = self._create_sample_map(
            spot_id,
            width=4,
            height=2,
            objects=[self._create_player_object(player_id, 0, 0)],
        )
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="location",
                    target_spot_id=spot_id,
                    target_location_area_id=10,
                )
            )

        assert result.success is True
        assert result.path_found is True
        assert result.temp_goal is not None
        assert result.path is not None
        assert len(result.path) > 0
        assert result.goal_destination_type == "location"
        assert result.goal_spot_id == SpotId(spot_id)
        assert result.goal_location_area_id == LocationAreaId(10)

    def test_resolve_and_calculate_path_location_already_in_area(
        self, setup_service
    ):
        """既にロケーション内にいるとき、already_at_destination で成功を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 2, 0))

        location_area = LocationArea(
            location_id=LocationAreaId(10),
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
            name="Goal",
            description="",
        )
        phys_map = self._create_sample_map(
            spot_id, objects=[self._create_player_object(player_id, 2, 0)]
        )
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="location",
                    target_spot_id=spot_id,
                    target_location_area_id=10,
                )
            )

        assert result.success is True
        assert result.already_at_destination is True
        assert result.path_found is False
        assert "既に目的地のロケーションにいます" in result.message

    def test_resolve_and_calculate_path_object_already_adjacent(
        self, setup_service
    ):
        """既にオブジェクトに隣接しているとき、already_at_destination で成功を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        target_obj_id = 100
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        target_obj = WorldObject(
            object_id=WorldObjectId.create(target_obj_id),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.NPC,
        )
        phys_map = self._create_sample_map(
            spot_id,
            width=4,
            height=2,
            objects=[
                self._create_player_object(player_id, 0, 0),
                target_obj,
            ],
        )
        phys_repo.save(phys_map)

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="object",
                    target_spot_id=spot_id,
                    target_world_object_id=target_obj_id,
                )
            )

        assert result.success is True
        assert result.already_at_destination is True
        assert result.path_found is False
        assert "既に目標オブジェクトの傍にいます" in result.message

    def test_resolve_and_calculate_path_object_path_found(self, setup_service):
        """オブジェクトへ経路を計算する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        target_obj_id = 100
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        target_obj = WorldObject(
            object_id=WorldObjectId.create(target_obj_id),
            coordinate=Coordinate(3, 0, 0),
            object_type=ObjectTypeEnum.NPC,
        )
        phys_map = self._create_sample_map(
            spot_id,
            width=4,
            height=2,
            objects=[
                self._create_player_object(player_id, 0, 0),
                target_obj,
            ],
        )
        phys_repo.save(phys_map)

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="object",
                    target_spot_id=spot_id,
                    target_world_object_id=target_obj_id,
                )
            )

        assert result.success is True
        assert result.path_found is True
        assert result.temp_goal is not None
        assert result.path is not None
        assert result.goal_destination_type == "object"
        assert result.goal_world_object_id == WorldObjectId.create(target_obj_id)

    def test_resolve_and_calculate_path_path_not_found(self, setup_service):
        """経路が見つからないとき、success=False を返す。（ロケーションが壁で囲まれている場合）"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        location_area = LocationArea(
            location_id=LocationAreaId(10),
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
            name="Goal",
            description="",
        )
        wall_tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.grass()),
            Coordinate(2, 0, 0): Tile(Coordinate(2, 0, 0), TerrainType.wall()),
        }
        phys_map = PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=wall_tiles,
            objects=[self._create_player_object(player_id, 0, 0)],
            gateways=[],
        )
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="location",
                    target_spot_id=spot_id,
                    target_location_area_id=10,
                )
            )

        assert result.success is False
        assert result.path_found is False
        assert "経路が見つかりません" in result.message

    def test_resolve_and_calculate_path_object_no_passable_adjacent(
        self, setup_service
    ):
        """オブジェクト周囲に通行可能セルがないとき、success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        target_obj_id = 100
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        target_obj = WorldObject(
            object_id=WorldObjectId.create(target_obj_id),
            coordinate=Coordinate(1, 1, 0),
            object_type=ObjectTypeEnum.NPC,
        )
        tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall()),
            Coordinate(0, 1, 0): Tile(Coordinate(0, 1, 0), TerrainType.wall()),
            Coordinate(1, 1, 0): Tile(Coordinate(1, 1, 0), TerrainType.grass()),
            Coordinate(2, 1, 0): Tile(Coordinate(2, 1, 0), TerrainType.wall()),
            Coordinate(1, 2, 0): Tile(Coordinate(1, 2, 0), TerrainType.wall()),
        }
        phys_map = PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=[self._create_player_object(player_id, 0, 0), target_obj],
            gateways=[],
        )
        phys_repo.save(phys_map)

        with uow:
            result = svc.resolve_and_calculate_path(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="object",
                    target_spot_id=spot_id,
                    target_world_object_id=target_obj_id,
                )
            )

        assert result.success is False
        assert result.path_found is False
        assert "通行可能な場所がありません" in result.message

    # --- resolve_and_calculate_path 例外系 ---

    def test_resolve_and_calculate_path_player_not_found_raises(self, setup_service):
        """プレイヤーが存在しないとき PlayerNotFoundException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 999

        self._register_spots(spot_repo, [{"id": 1, "name": "Spot 1"}])

        with uow:
            with pytest.raises(PlayerNotFoundException):
                svc.resolve_and_calculate_path(
                    SetDestinationCommand(
                        player_id=player_id,
                        destination_type="spot",
                        target_spot_id=1,
                    )
                )

    def test_resolve_and_calculate_path_player_not_on_map_raises(self, setup_service):
        """プレイヤーがマップに配置されていないとき MovementInvalidException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1

        self._register_spots(spot_repo, [{"id": 1, "name": "Spot 1"}])
        status = self._create_sample_status(
            player_id, navigation_state=PlayerNavigationState.empty()
        )
        status_repo.save(status)

        with uow:
            with pytest.raises(MovementInvalidException, match="not placed on any map"):
                svc.resolve_and_calculate_path(
                    SetDestinationCommand(
                        player_id=player_id,
                        destination_type="spot",
                        target_spot_id=1,
                    )
                )

    def test_resolve_and_calculate_path_location_area_not_found_raises(
        self, setup_service
    ):
        """存在しないロケーションエリアを指定したとき MovementInvalidException を送出する。
        LocationAreaNotFoundException をキャッチし MovementInvalidException に変換する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            with pytest.raises(MovementInvalidException, match="Location area.*not found"):
                svc.resolve_and_calculate_path(
                    SetDestinationCommand(
                        player_id=player_id,
                        destination_type="location",
                        target_spot_id=spot_id,
                        target_location_area_id=999,
                    )
                )

    def test_resolve_and_calculate_path_unexpected_exception_from_get_location_area_propagates(
        self, setup_service
    ):
        """get_location_area が LocationAreaNotFoundException 以外を投げたときは伝播する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        location_area = LocationArea(
            location_id=LocationAreaId(10),
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
            name="Goal",
            description="",
        )
        phys_map = self._create_sample_map(
            spot_id,
            width=4,
            height=2,
            objects=[self._create_player_object(player_id, 0, 0)],
        )
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)

        with patch.object(
            PhysicalMapAggregate,
            "get_location_area",
            side_effect=RuntimeError("unexpected error from aggregate"),
        ):
            with uow:
                with pytest.raises(RuntimeError, match="unexpected error from aggregate"):
                    svc.resolve_and_calculate_path(
                        SetDestinationCommand(
                            player_id=player_id,
                            destination_type="location",
                            target_spot_id=spot_id,
                            target_location_area_id=10,
                        )
                    )

    def test_resolve_and_calculate_path_object_not_found_raises(self, setup_service):
        """存在しないオブジェクトを指定したとき MovementInvalidException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            with pytest.raises(MovementInvalidException, match="Object.*not found"):
                svc.resolve_and_calculate_path(
                    SetDestinationCommand(
                        player_id=player_id,
                        destination_type="object",
                        target_spot_id=spot_id,
                        target_world_object_id=999,
                    )
                )

    def test_resolve_and_calculate_path_map_not_found_raises(self, setup_service):
        """スポットに対応するマップが存在しないとき MapNotFoundException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1
        nonexistent_spot_id = 999

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            with pytest.raises(MapNotFoundException):
                svc.resolve_and_calculate_path(
                    SetDestinationCommand(
                        player_id=player_id,
                        destination_type="location",
                        target_spot_id=nonexistent_spot_id,
                        target_location_area_id=1,
                    )
                )

    # --- calculate_path_to_coordinate 正常系 ---

    def test_calculate_path_to_coordinate_path_planned(self, setup_service):
        """座標指定で経路計算が成功する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with uow:
            result = svc.calculate_path_to_coordinate(
                player_id=player_id,
                target_spot_id=SpotId(spot_id),
                target_coordinate=Coordinate(3, 0, 0),
            )

        assert result.success is True
        assert result.path_planned is True
        assert result.already_at_destination is False
        assert result.temp_goal is not None
        assert result.path is not None
        assert result.goal_spot_id == SpotId(spot_id)

    def test_calculate_path_to_coordinate_already_at_destination(
        self, setup_service
    ):
        """既に目標座標にいるとき、already_at_destination で成功を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 2, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id, objects=[self._create_player_object(player_id, 2, 0)]
            )
        )

        with uow:
            result = svc.calculate_path_to_coordinate(
                player_id=player_id,
                target_spot_id=SpotId(spot_id),
                target_coordinate=Coordinate(2, 0, 0),
            )

        assert result.success is True
        assert result.path_planned is False
        assert result.already_at_destination is True
        assert "既に追跡先座標にいます" in result.message

    def test_calculate_path_to_coordinate_path_not_found(self, setup_service):
        """経路が見つからないとき、success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))

        wall_tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall()),
            Coordinate(2, 0, 0): Tile(Coordinate(2, 0, 0), TerrainType.wall()),
        }
        phys_map = PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=wall_tiles,
            objects=[self._create_player_object(player_id, 0, 0)],
            gateways=[],
        )
        phys_repo.save(phys_map)

        with uow:
            result = svc.calculate_path_to_coordinate(
                player_id=player_id,
                target_spot_id=SpotId(spot_id),
                target_coordinate=Coordinate(2, 0, 0),
            )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_handled(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_handled(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_handled(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path to target"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    def test_calculate_path_to_coordinate_path_not_found_exception_returns_failure(
        self, setup_service
    ):
        """calculate_global_path が PathNotFoundException を投げたとき success=False を返す。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )

        with patch.object(
            svc._global_pathfinding_service,
            "calculate_global_path",
            side_effect=PathNotFoundException("No path found"),
        ):
            with uow:
                result = svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id),
                    target_coordinate=Coordinate(3, 0, 0),
                )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        assert "経路が見つかりません" in result.message

    # --- calculate_path_to_coordinate 例外系 ---

    def test_calculate_path_to_coordinate_player_not_found_raises(
        self, setup_service
    ):
        """プレイヤーが存在しないとき PlayerNotFoundException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service

        self._register_spots(spot_repo, [{"id": 1, "name": "Spot 1"}])

        with uow:
            with pytest.raises(PlayerNotFoundException):
                svc.calculate_path_to_coordinate(
                    player_id=999,
                    target_spot_id=SpotId(1),
                    target_coordinate=Coordinate(1, 0, 0),
                )

    def test_calculate_path_to_coordinate_player_not_on_map_raises(
        self, setup_service
    ):
        """プレイヤーがマップに配置されていないとき MovementInvalidException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1

        self._register_spots(spot_repo, [{"id": 1, "name": "Spot 1"}])
        status = self._create_sample_status(
            player_id, navigation_state=PlayerNavigationState.empty()
        )
        status_repo.save(status)

        with uow:
            with pytest.raises(MovementInvalidException, match="not placed on any map"):
                svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(1),
                    target_coordinate=Coordinate(1, 0, 0),
                )

    def test_calculate_path_to_coordinate_map_not_found_raises(self, setup_service):
        """プレイヤー現在スポットに対応するマップが存在しないとき MapNotFoundException を送出する。"""
        svc, status_repo, phys_repo, spot_repo, uow = setup_service
        player_id = 1
        spot_id_without_map = 999

        self._register_spots(spot_repo, [{"id": spot_id_without_map, "name": "No Map Spot"}])
        status_repo.save(
            self._create_sample_status(player_id, spot_id_without_map, 0, 0)
        )
        phys_repo.save(
            self._create_sample_map(
                spot_id_without_map + 1,
                objects=[self._create_player_object(player_id)],
            )
        )

        with uow:
            with pytest.raises(MapNotFoundException):
                svc.calculate_path_to_coordinate(
                    player_id=player_id,
                    target_spot_id=SpotId(spot_id_without_map),
                    target_coordinate=Coordinate(1, 0, 0),
                )
