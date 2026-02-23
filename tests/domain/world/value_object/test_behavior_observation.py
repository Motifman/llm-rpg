"""BehaviorObservation 値オブジェクトのテスト"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
from ai_rpg_world.domain.world.value_object.behavior_context import (
    TargetSelectionContext,
    SkillSelectionContext,
    GrowthContext,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick


class TestBehaviorObservationCreation:
    """BehaviorObservation の正常・境界ケース"""

    def test_create_with_defaults(self):
        """デフォルトで空の観測で作成できること"""
        obs = BehaviorObservation()
        assert obs.visible_threats == []
        assert obs.visible_hostiles == []
        assert obs.selected_target is None
        assert obs.skill_context is None
        assert obs.growth_context is None
        assert obs.target_context is None
        assert obs.pack_rally_coordinate is None
        assert obs.current_tick is None

    def test_create_with_empty_lists_explicit(self):
        """明示的に空リストを渡して作成できること"""
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
        )
        assert obs.visible_threats == []
        assert obs.visible_hostiles == []
        assert obs.selected_target is None

    def test_create_with_skill_context(self):
        """skill_context を指定して作成できること"""
        skill_ctx = SkillSelectionContext(
            usable_slot_indices={0, 1},
            targets_in_range_by_slot={0: 2, 1: 1},
        )
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            skill_context=skill_ctx,
        )
        assert obs.skill_context is skill_ctx
        assert obs.skill_context.usable_slot_indices == {0, 1}

    def test_create_with_growth_context(self):
        """growth_context を指定して作成できること"""
        growth_ctx = GrowthContext(effective_flee_threshold=0.3, allow_chase=True)
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            growth_context=growth_ctx,
        )
        assert obs.growth_context is growth_ctx
        assert obs.growth_context.effective_flee_threshold == 0.3
        assert obs.growth_context.allow_chase is True

    def test_create_with_target_context(self):
        """target_context を指定して作成できること"""
        oid = WorldObjectId(1)
        target_ctx = TargetSelectionContext(
            hp_percentage_by_id={oid: 0.5},
            threat_by_id={oid: 10},
        )
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            target_context=target_ctx,
        )
        assert obs.target_context is target_ctx
        assert obs.target_context.threat_by_id[oid] == 10

    def test_create_with_pack_rally_coordinate(self):
        """pack_rally_coordinate を指定して作成できること"""
        rally = Coordinate(8, 5)
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            pack_rally_coordinate=rally,
        )
        assert obs.pack_rally_coordinate == rally
        assert obs.pack_rally_coordinate.x == 8
        assert obs.pack_rally_coordinate.y == 5

    def test_create_with_current_tick(self):
        """current_tick を指定して作成できること"""
        tick = WorldTick(100)
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            current_tick=tick,
        )
        assert obs.current_tick is tick
        assert obs.current_tick.value == 100

    def test_create_with_selected_target(self):
        """selected_target（WorldObject のモック）を指定して作成できること"""
        target = MagicMock()
        target.object_id = WorldObjectId(1)
        target.coordinate = Coordinate(3, 4)
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=target,
        )
        assert obs.selected_target is target
        assert obs.selected_target.object_id == WorldObjectId(1)

    def test_create_with_visible_threats_and_hostiles(self):
        """visible_threats / visible_hostiles にオブジェクトリストを指定して作成できること"""
        obj1 = MagicMock()
        obj1.object_id = WorldObjectId(10)
        obj2 = MagicMock()
        obj2.object_id = WorldObjectId(20)
        obs = BehaviorObservation(
            visible_threats=[obj1],
            visible_hostiles=[obj1, obj2],
            selected_target=obj2,
        )
        assert len(obs.visible_threats) == 1
        assert obs.visible_threats[0].object_id == WorldObjectId(10)
        assert len(obs.visible_hostiles) == 2
        assert obs.selected_target is obj2


class TestBehaviorObservationImmutability:
    """BehaviorObservation の不変性（frozen）"""

    def test_frozen_visible_threats_assign_raises(self):
        """visible_threats への代入ができないこと（frozen）"""
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
        )
        with pytest.raises(AttributeError):
            obs.visible_threats = [MagicMock()]

    def test_frozen_selected_target_assign_raises(self):
        """selected_target への代入ができないこと（frozen）"""
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
        )
        with pytest.raises(AttributeError):
            obs.selected_target = MagicMock()

    def test_frozen_current_tick_assign_raises(self):
        """current_tick への代入ができないこと（frozen）"""
        obs = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
        )
        with pytest.raises(AttributeError):
            obs.current_tick = WorldTick(1)


class TestBehaviorObservationEquality:
    """BehaviorObservation の等価性・同一性"""

    def test_same_values_equality(self):
        """同じ内容の観測は等しいこと（値の比較）"""
        coord = Coordinate(1, 1)
        obs1 = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            pack_rally_coordinate=coord,
        )
        obs2 = BehaviorObservation(
            visible_threats=[],
            visible_hostiles=[],
            selected_target=None,
            pack_rally_coordinate=coord,
        )
        assert obs1.pack_rally_coordinate == obs2.pack_rally_coordinate
        assert obs1.visible_threats == obs2.visible_threats
        assert obs1.visible_hostiles == obs2.visible_hostiles
