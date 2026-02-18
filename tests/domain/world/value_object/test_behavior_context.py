"""行動コンテキスト（TargetSelectionContext, SkillSelectionContext, GrowthContext, PlanActionContext）のテスト"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.domain.world.value_object.behavior_context import (
    TargetSelectionContext,
    SkillSelectionContext,
    GrowthContext,
    PlanActionContext,
)
from ai_rpg_world.domain.world.exception.behavior_exception import GrowthContextValidationException
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


class TestTargetSelectionContext:
    """TargetSelectionContext の正常・境界"""

    def test_create_empty_defaults(self):
        """デフォルトで空の辞書で作成できること"""
        ctx = TargetSelectionContext()
        assert ctx.hp_percentage_by_id == {}
        assert ctx.threat_by_id == {}

    def test_create_with_data(self):
        """HP%・脅威値を指定して作成できること"""
        oid = WorldObjectId(1)
        ctx = TargetSelectionContext(
            hp_percentage_by_id={oid: 0.5},
            threat_by_id={oid: 10},
        )
        assert ctx.hp_percentage_by_id[oid] == 0.5
        assert ctx.threat_by_id[oid] == 10


class TestSkillSelectionContext:
    """SkillSelectionContext の正常・境界"""

    def test_create_empty_defaults(self):
        """デフォルトで空の set/dict で作成できること"""
        ctx = SkillSelectionContext()
        assert ctx.usable_slot_indices == set()
        assert ctx.targets_in_range_by_slot == {}

    def test_create_with_data(self):
        """使用可能スロット・射程内数を指定して作成できること"""
        ctx = SkillSelectionContext(
            usable_slot_indices={0, 1},
            targets_in_range_by_slot={0: 2, 1: 1},
        )
        assert ctx.usable_slot_indices == {0, 1}
        assert ctx.targets_in_range_by_slot[0] == 2
        assert ctx.targets_in_range_by_slot[1] == 1


class TestGrowthContext:
    """GrowthContext の正常ケース"""

    def test_create_success_minimal(self):
        """有効な最小値で作成できること"""
        ctx = GrowthContext(effective_flee_threshold=0.0, allow_chase=True)
        assert ctx.effective_flee_threshold == 0.0
        assert ctx.allow_chase is True

    def test_create_success_boundary_flee_threshold(self):
        """effective_flee_threshold の境界値 0.0 と 1.0 で作成できること"""
        ctx_low = GrowthContext(effective_flee_threshold=0.0, allow_chase=True)
        ctx_high = GrowthContext(effective_flee_threshold=1.0, allow_chase=False)
        assert ctx_low.effective_flee_threshold == 0.0
        assert ctx_high.effective_flee_threshold == 1.0
        assert ctx_high.allow_chase is False

    def test_create_success_mid_value(self):
        """中間値で作成できること"""
        ctx = GrowthContext(effective_flee_threshold=0.3, allow_chase=True)
        assert ctx.effective_flee_threshold == 0.3
        assert ctx.allow_chase is True

    def test_create_success_allow_chase_false(self):
        """allow_chase=False（幼体など）で作成できること"""
        ctx = GrowthContext(effective_flee_threshold=0.5, allow_chase=False)
        assert ctx.allow_chase is False


class TestGrowthContextValidation:
    """GrowthContext のバリデーション（例外ケース）"""

    def test_effective_flee_threshold_negative_raises(self):
        """effective_flee_threshold が負の場合は GrowthContextValidationException を投げること"""
        with pytest.raises(GrowthContextValidationException, match="effective_flee_threshold must be between 0.0 and 1.0"):
            GrowthContext(effective_flee_threshold=-0.1, allow_chase=True)

    def test_effective_flee_threshold_over_one_raises(self):
        """effective_flee_threshold が 1.0 を超える場合は GrowthContextValidationException を投げること"""
        with pytest.raises(GrowthContextValidationException, match="effective_flee_threshold must be between 0.0 and 1.0"):
            GrowthContext(effective_flee_threshold=1.01, allow_chase=True)

    def test_effective_flee_threshold_not_number_raises(self):
        """effective_flee_threshold が数値でない場合は GrowthContextValidationException を投げること"""
        with pytest.raises(GrowthContextValidationException, match="effective_flee_threshold must be a number"):
            GrowthContext(effective_flee_threshold="0.5", allow_chase=True)

    def test_allow_chase_not_bool_raises(self):
        """allow_chase が bool でない場合は GrowthContextValidationException を投げること"""
        with pytest.raises(GrowthContextValidationException, match="allow_chase must be a bool"):
            GrowthContext(effective_flee_threshold=0.2, allow_chase=1)


class TestPlanActionContext:
    """PlanActionContext の event_sink のテスト"""

    def test_create_with_default_event_sink(self):
        """event_sink を渡さない場合、デフォルトで空リストが設定されること"""
        actor_id = WorldObjectId(1)
        actor = MagicMock()
        actor.object_id = actor_id
        actor.coordinate = Coordinate(0, 0)
        map_aggregate = MagicMock()
        component = MagicMock()
        ctx = PlanActionContext(
            actor_id=actor_id,
            actor=actor,
            map_aggregate=map_aggregate,
            component=component,
            visible_threats=[],
            visible_hostiles=[],
            target=None,
        )
        assert ctx.event_sink == []
        assert isinstance(ctx.event_sink, list)

    def test_create_with_custom_event_sink(self):
        """event_sink を渡した場合、そのリストがそのまま使われること"""
        actor_id = WorldObjectId(1)
        actor = MagicMock()
        actor.object_id = actor_id
        actor.coordinate = Coordinate(0, 0)
        map_aggregate = MagicMock()
        component = MagicMock()
        sink = []
        ctx = PlanActionContext(
            actor_id=actor_id,
            actor=actor,
            map_aggregate=map_aggregate,
            component=component,
            visible_threats=[],
            visible_hostiles=[],
            target=None,
            event_sink=sink,
        )
        assert ctx.event_sink is sink
        ctx.event_sink.append("dummy")
        assert sink == ["dummy"]
