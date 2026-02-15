"""TargetSelectionPolicy のテスト"""

import pytest
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, AutonomousBehaviorComponent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_context import TargetSelectionContext
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.service.target_selection_policy import (
    TargetSelectionPolicy,
    NearestTargetPolicy,
    HighestThreatTargetPolicy,
    LowestHpTargetPolicy,
    PreyPriorityTargetPolicy,
)
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService
from ai_rpg_world.domain.world.enum.world_enum import Disposition


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


class TestHighestThreatTargetPolicy:
    """HighestThreatTargetPolicy の正常・境界・context 有無のテスト"""

    @pytest.fixture
    def policy(self) -> HighestThreatTargetPolicy:
        return HighestThreatTargetPolicy()

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
    def candidate_low_threat(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    @pytest.fixture
    def candidate_high_threat(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(2),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    def test_select_target_returns_none_when_empty(self, policy, actor):
        """候補が空のとき None を返すこと"""
        result = policy.select_target(actor, [])
        assert result is None

    def test_select_target_without_context_returns_nearest(self, policy, actor, candidate_low_threat, candidate_high_threat):
        """context がないときは最近距離の候補を返すこと（NearestTargetPolicy と同様）"""
        candidates = [candidate_high_threat, candidate_low_threat]
        result = policy.select_target(actor, candidates)
        assert result is not None
        assert result.object_id == WorldObjectId(1)
        assert result.coordinate == Coordinate(6, 5)

    def test_select_target_with_threat_by_id_returns_highest_threat(self, policy, actor, candidate_low_threat, candidate_high_threat):
        """context.threat_by_id があるときは脅威値が最も高い候補を返すこと"""
        context = TargetSelectionContext(threat_by_id={
            WorldObjectId(1): 10,
            WorldObjectId(2): 50,
        })
        candidates = [candidate_low_threat, candidate_high_threat]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id == WorldObjectId(2)

    def test_select_target_threat_tie_returns_one(self, policy, actor, candidate_low_threat, candidate_high_threat):
        """脅威値が同点の候補が複数いる場合でも1体を返すこと"""
        context = TargetSelectionContext(threat_by_id={
            WorldObjectId(1): 30,
            WorldObjectId(2): 30,
        })
        candidates = [candidate_low_threat, candidate_high_threat]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id in (WorldObjectId(1), WorldObjectId(2))

    def test_select_target_missing_id_in_threat_uses_zero(self, policy, actor, candidate_low_threat, candidate_high_threat):
        """threat_by_id に含まれない ID は脅威 0 として扱うこと"""
        context = TargetSelectionContext(threat_by_id={WorldObjectId(2): 5})
        candidates = [candidate_low_threat, candidate_high_threat]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id == WorldObjectId(2)

    def test_select_target_empty_threat_by_id_falls_back_to_nearest(self, policy, actor, candidate_low_threat, candidate_high_threat):
        """context はあるが threat_by_id が空のときは最近距離を返すこと"""
        context = TargetSelectionContext(threat_by_id={})
        candidates = [candidate_high_threat, candidate_low_threat]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id == WorldObjectId(1)


class TestLowestHpTargetPolicy:
    """LowestHpTargetPolicy の正常・境界・context 有無のテスト"""

    @pytest.fixture
    def policy(self) -> LowestHpTargetPolicy:
        return LowestHpTargetPolicy()

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
            coordinate=Coordinate(8, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    def test_select_target_returns_none_when_empty(self, policy, actor):
        """候補が空のとき None を返すこと"""
        result = policy.select_target(actor, [])
        assert result is None

    def test_select_target_without_context_returns_nearest(self, policy, actor, candidate_near, candidate_far):
        """context がないときは最近距離の候補を返すこと"""
        candidates = [candidate_far, candidate_near]
        result = policy.select_target(actor, candidates)
        assert result is not None
        assert result.object_id == WorldObjectId(1)

    def test_select_target_with_hp_percentage_returns_lowest_hp(self, policy, actor, candidate_near, candidate_far):
        """context.hp_percentage_by_id があるときは HP% が最も低い候補を返すこと"""
        context = TargetSelectionContext(hp_percentage_by_id={
            WorldObjectId(1): 0.8,
            WorldObjectId(2): 0.2,
        })
        candidates = [candidate_near, candidate_far]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id == WorldObjectId(2)

    def test_select_target_hp_tie_returns_one(self, policy, actor, candidate_near, candidate_far):
        """HP% が同点の候補が複数いる場合でも1体を返すこと"""
        context = TargetSelectionContext(hp_percentage_by_id={
            WorldObjectId(1): 0.5,
            WorldObjectId(2): 0.5,
        })
        candidates = [candidate_near, candidate_far]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id in (WorldObjectId(1), WorldObjectId(2))

    def test_select_target_missing_id_in_hp_uses_one(self, policy, actor, candidate_near, candidate_far):
        """hp_percentage_by_id に含まれない ID は 1.0 として扱うこと（満タン）"""
        context = TargetSelectionContext(hp_percentage_by_id={WorldObjectId(1): 0.1})
        candidates = [candidate_near, candidate_far]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id == WorldObjectId(1)

    def test_select_target_empty_hp_percentage_falls_back_to_nearest(self, policy, actor, candidate_near, candidate_far):
        """context はあるが hp_percentage_by_id が空のときは最近距離を返すこと"""
        context = TargetSelectionContext(hp_percentage_by_id={})
        candidates = [candidate_far, candidate_near]
        result = policy.select_target(actor, candidates, context)
        assert result is not None
        assert result.object_id == WorldObjectId(1)


class TestPreyPriorityTargetPolicy:
    """PreyPriorityTargetPolicy の正常・境界ケース"""

    @pytest.fixture
    def hostility_service(self):
        return ConfigurableHostilityService(
            race_disposition_table={
                "wolf": {"rabbit": Disposition.PREY, "human": Disposition.HOSTILE},
            }
        )

    @pytest.fixture
    def policy(self, hostility_service):
        return PreyPriorityTargetPolicy(hostility_service, NearestTargetPolicy())

    @pytest.fixture
    def actor(self) -> WorldObject:
        comp = AutonomousBehaviorComponent(race="wolf", vision_range=5)
        return WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(5, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=comp,
        )

    @pytest.fixture
    def candidate_prey(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(201),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=AutonomousBehaviorComponent(race="rabbit"),
        )

    @pytest.fixture
    def candidate_hostile(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    def test_select_target_returns_none_when_empty(self, policy, actor):
        """候補が空のとき None を返すこと"""
        result = policy.select_target(actor, [])
        assert result is None

    def test_select_target_prefers_prey_over_hostile(self, policy, actor, candidate_prey, candidate_hostile):
        """PREY を HOSTILE より優先して選択すること（獲物が遠くても選ぶ）"""
        candidates = [candidate_hostile, candidate_prey]
        result = policy.select_target(actor, candidates)
        assert result is not None
        assert result.object_id == WorldObjectId(201)

    def test_select_target_falls_back_when_no_prey(self, policy, actor, candidate_hostile):
        """獲物がいないときはフォールバック（最近距離）で選ぶこと"""
        candidate_far = WorldObject(
            object_id=WorldObjectId(2),
            coordinate=Coordinate(9, 9),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        candidates = [candidate_far, candidate_hostile]
        result = policy.select_target(actor, candidates)
        assert result is not None
        assert result.object_id == WorldObjectId(1)

    def test_select_target_single_prey_returns_it(self, policy, actor, candidate_prey):
        """獲物が1体だけのときその1体を返すこと"""
        result = policy.select_target(actor, [candidate_prey])
        assert result is not None
        assert result.object_id == WorldObjectId(201)
