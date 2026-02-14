"""TargetSelectionPolicy のテスト"""

import pytest
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, AutonomousBehaviorComponent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.service.target_selection_policy import (
    TargetSelectionPolicy,
    NearestTargetPolicy,
)


class TestNearestTargetPolicy:
    """NearestTargetPolicy の正常・境界・例外ケース"""

    @pytest.fixture
    def policy(self) -> NearestTargetPolicy:
        return NearestTargetPolicy()

    @pytest.fixture
    def actor(self) -> WorldObject:
        comp = AutonomousBehaviorComponent(vision_range=5)
        return WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )

    @pytest.fixture
    def candidate_near(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    @pytest.fixture
    def candidate_far(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(2),
            coordinate=Coordinate(9, 9),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    def test_select_target_returns_none_when_empty(self, policy, actor):
        """候補が空のとき None を返すこと"""
        result = policy.select_target(actor, [])
        assert result is None

    def test_select_target_returns_single_candidate(self, policy, actor, candidate_near):
        """候補が1体のときその候補を返すこと"""
        result = policy.select_target(actor, [candidate_near])
        assert result is not None
        assert result.object_id == candidate_near.object_id
        assert result.coordinate == Coordinate(6, 5)

    def test_select_target_returns_nearest_by_euclidean_distance(
        self, policy, actor, candidate_near, candidate_far
    ):
        """複数候補のとき最も近い1体を返すこと（ユークリッド距離）"""
        candidates = [candidate_far, candidate_near]
        result = policy.select_target(actor, candidates)
        assert result is not None
        assert result.object_id == candidate_near.object_id
        assert result.coordinate == Coordinate(6, 5)

    def test_select_target_order_independent(self, policy, actor, candidate_near, candidate_far):
        """候補の並び順に依存せず最近距離を選ぶこと"""
        candidates = [candidate_far, candidate_near]
        result1 = policy.select_target(actor, candidates)
        result2 = policy.select_target(actor, list(reversed(candidates)))
        assert result1 is not None and result2 is not None
        assert result1.object_id == result2.object_id

    def test_select_target_same_distance_returns_one(self, policy, actor):
        """同じ距離の候補が複数いる場合でも1体を返すこと"""
        c1 = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        c2 = WorldObject(
            object_id=WorldObjectId(2),
            coordinate=Coordinate(5, 6),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        result = policy.select_target(actor, [c1, c2])
        assert result is not None
        assert result.object_id in (WorldObjectId(1), WorldObjectId(2))

    def test_select_target_z_axis_considered(self, policy, actor):
        """Z軸を含む距離で比較すること"""
        comp = AutonomousBehaviorComponent(vision_range=5)
        actor_3d = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )
        near_z = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 1),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        far_xy = WorldObject(
            object_id=WorldObjectId(2),
            coordinate=Coordinate(3, 4, 0),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        result = policy.select_target(actor_3d, [far_xy, near_z])
        assert result is not None
        assert result.object_id == near_z.object_id
