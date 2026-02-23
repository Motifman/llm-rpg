"""MonsterActionResolverImpl のテスト。経路計算失敗時のスキップとログを検証する。"""

import pytest
from unittest.mock import Mock, MagicMock

from ai_rpg_world.application.world.services.monster_action_resolver import (
    MonsterActionResolverImpl,
)
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    PathNotFoundException,
    InvalidPathRequestException,
)
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType


@pytest.fixture
def map_aggregate():
    tiles = [Tile(Coordinate(0, 0, 0), TerrainType.grass())]
    return PhysicalMapAggregate.create(SpotId(1), tiles)


@pytest.fixture
def actor(map_aggregate):
    comp = AutonomousBehaviorComponent(vision_range=5)
    obj = WorldObject(
        object_id=WorldObjectId(1),
        coordinate=Coordinate(0, 0, 0),
        object_type=ObjectTypeEnum.NPC,
        is_blocking=False,
        component=comp,
    )
    map_aggregate.add_object(obj)
    return obj


@pytest.fixture
def pathfinding_service():
    return Mock()


@pytest.fixture
def skill_policy():
    return Mock()


class TestMonsterActionResolverGetNextStepTo:
    """_get_next_step_to の経路計算失敗時の挙動"""

    def test_returns_none_when_path_not_found(self, map_aggregate, actor, pathfinding_service, skill_policy):
        """PathNotFoundException 時は None を返し、例外は伝播しない"""
        pathfinding_service.calculate_path.side_effect = PathNotFoundException("No path")
        resolver = MonsterActionResolverImpl(
            map_aggregate, pathfinding_service, skill_policy, actor
        )
        start = Coordinate(0, 0, 0)
        goal = Coordinate(5, 5, 0)
        result = resolver._get_next_step_to(start, goal)
        assert result is None
        pathfinding_service.calculate_path.assert_called_once()

    def test_returns_none_when_invalid_path_request(self, map_aggregate, actor, pathfinding_service, skill_policy):
        """InvalidPathRequestException 時は None を返し、例外は伝播しない"""
        pathfinding_service.calculate_path.side_effect = InvalidPathRequestException("Invalid request")
        resolver = MonsterActionResolverImpl(
            map_aggregate, pathfinding_service, skill_policy, actor
        )
        start = Coordinate(0, 0, 0)
        goal = Coordinate(5, 5, 0)
        result = resolver._get_next_step_to(start, goal)
        assert result is None
        pathfinding_service.calculate_path.assert_called_once()

    def test_logs_debug_when_path_fails(self, map_aggregate, actor, pathfinding_service, skill_policy):
        """経路計算失敗時にデバッグログが出力される"""
        pathfinding_service.calculate_path.side_effect = PathNotFoundException("No path")
        resolver = MonsterActionResolverImpl(
            map_aggregate, pathfinding_service, skill_policy, actor
        )
        resolver._logger = MagicMock()
        start = Coordinate(1, 2, 0)
        goal = Coordinate(3, 4, 0)
        resolver._get_next_step_to(start, goal)
        resolver._logger.debug.assert_called_once()
        call_args = resolver._logger.debug.call_args
        assert "Path calculation failed" in call_args[0][0]
        assert call_args[0][1] == start
        assert call_args[0][2] == goal
        assert "No path" in str(call_args[0][3])