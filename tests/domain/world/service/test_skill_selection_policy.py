"""SkillSelectionPolicy のテスト"""

import pytest
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
    MonsterSkillInfo,
)
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.service.skill_selection_policy import (
    SkillSelectionPolicy,
    FirstInRangeSkillPolicy,
)


class TestFirstInRangeSkillPolicy:
    """FirstInRangeSkillPolicy の正常・境界・例外ケース"""

    @pytest.fixture
    def policy(self) -> FirstInRangeSkillPolicy:
        return FirstInRangeSkillPolicy()

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
    def target_in_range(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    @pytest.fixture
    def target_out_of_range(self) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(20, 20),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )

    def test_select_slot_returns_none_when_no_skills(self, policy, actor, target_in_range):
        """スキルが空のとき None を返すこと"""
        result = policy.select_slot(actor, target_in_range, [])
        assert result is None

    def test_select_slot_returns_none_when_all_out_of_range(
        self, policy, actor, target_out_of_range
    ):
        """すべて射程外のとき None を返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=1, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=2, mp_cost=20),
        ]
        result = policy.select_slot(actor, target_out_of_range, skills)
        assert result is None

    def test_select_slot_returns_first_in_range(self, policy, actor, target_in_range):
        """射程内の最初のスキルの slot_index を返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=10, mp_cost=20),
        ]
        result = policy.select_slot(actor, target_in_range, skills)
        assert result == 0

    def test_select_slot_skips_out_of_range_then_returns_next(self, policy, actor, target_in_range):
        """先頭が射程外で2つ目が射程内の場合、2つ目の slot_index を返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=0, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        result = policy.select_slot(actor, target_in_range, skills)
        assert result == 1

    def test_select_slot_exactly_at_range(self, policy, actor):
        """距離が射程と一致する場合にそのスキルを選ぶこと（マンハッタン距離）"""
        target = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(6, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        skills = [MonsterSkillInfo(slot_index=0, range=1, mp_cost=10)]
        result = policy.select_slot(actor, target, skills)
        assert result == 0

    def test_select_slot_single_skill_in_range(self, policy, actor, target_in_range):
        """スキルが1つのみで射程内のときその slot_index を返すこと"""
        skills = [MonsterSkillInfo(slot_index=2, range=10, mp_cost=15)]
        result = policy.select_slot(actor, target_in_range, skills)
        assert result == 2

    def test_select_slot_z_axis_in_distance(self, policy):
        """Z軸を含む距離で射程判定すること"""
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.NPC,
            is_blocking=False,
            component=AutonomousBehaviorComponent(vision_range=5),
        )
        target = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(0, 0, 1),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        skills = [MonsterSkillInfo(slot_index=0, range=1, mp_cost=10)]
        result = policy.select_slot(actor, target, skills)
        assert result == 0
