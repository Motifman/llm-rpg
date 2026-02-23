"""SkillSelectionPolicy のテスト"""

import pytest
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
)
from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.behavior_context import SkillSelectionContext
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.service.skill_selection_policy import (
    SkillSelectionPolicy,
    FirstInRangeSkillPolicy,
    BossSkillPolicy,
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

    def test_select_slot_with_usable_slot_indices_restricts_to_slot(self, policy, actor, target_in_range):
        """context.usable_slot_indices で指定したスロットのみから選ぶこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        context = SkillSelectionContext(usable_slot_indices={1})
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result == 1

    def test_select_slot_with_usable_slot_indices_none_in_range_returns_none(self, policy, actor):
        """使用可能スロットが射程内にないとき None を返すこと"""
        target_far = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=1, mp_cost=20),
        ]
        context = SkillSelectionContext(usable_slot_indices={1})
        result = policy.select_slot(actor, target_far, skills, context)
        assert result is None

    def test_select_slot_with_empty_usable_slot_indices_returns_none(self, policy, actor, target_in_range):
        """usable_slot_indices が空集合のときどのスロットも選ばれず None を返すこと"""
        skills = [MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)]
        context = SkillSelectionContext(usable_slot_indices=set())
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result is None

    def test_select_slot_with_context_none_ignores_usable(self, policy, actor, target_in_range):
        """context が None のとき usable_slot_indices は無視され射程内の最初のスキルを返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        result = policy.select_slot(actor, target_in_range, skills, None)
        assert result == 0


class TestBossSkillPolicy:
    """BossSkillPolicy の正常・境界・context 有無・AOE優先のテスト"""

    @pytest.fixture
    def policy(self) -> BossSkillPolicy:
        return BossSkillPolicy()

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

    def test_select_slot_returns_none_when_all_out_of_range(self, policy, actor, target_out_of_range):
        """すべて射程外のとき None を返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=1, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=2, mp_cost=20),
        ]
        result = policy.select_slot(actor, target_out_of_range, skills)
        assert result is None

    def test_select_slot_without_context_returns_first_in_range(self, policy, actor, target_in_range):
        """context がないときは射程内の最初のスキルを返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=10, mp_cost=20),
        ]
        result = policy.select_slot(actor, target_in_range, skills)
        assert result == 0

    def test_select_slot_with_targets_in_range_by_slot_returns_aoe_priority(self, policy, actor, target_in_range):
        """targets_in_range_by_slot があるときは射程内ターゲット数が最大のスロットを返すこと（AOE優先）"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        context = SkillSelectionContext(
            usable_slot_indices={0, 1},
            targets_in_range_by_slot={0: 1, 1: 3},
        )
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result == 1

    def test_select_slot_with_usable_slot_indices_filters_slots(self, policy, actor, target_in_range):
        """usable_slot_indices で使用可能スロットに絞り、その中から選ぶこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        context = SkillSelectionContext(usable_slot_indices={1})
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result == 1

    def test_select_slot_usable_slot_none_in_range_returns_none(self, policy, actor):
        """使用可能スロットが射程内にないとき None を返すこと"""
        target_far = WorldObject(
            object_id=WorldObjectId(1),
            coordinate=Coordinate(7, 5),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(race="human"),
        )
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=1, mp_cost=20),
        ]
        context = SkillSelectionContext(usable_slot_indices={1})
        result = policy.select_slot(actor, target_far, skills, context)
        assert result is None

    def test_select_slot_targets_by_slot_missing_slot_uses_zero(self, policy, actor, target_in_range):
        """targets_in_range_by_slot に含まれないスロットは 0 として扱うこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        context = SkillSelectionContext(
            usable_slot_indices={0, 1},
            targets_in_range_by_slot={1: 2},
        )
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result == 1

    def test_select_slot_empty_targets_by_slot_returns_first_in_range(self, policy, actor, target_in_range):
        """targets_in_range_by_slot が空のときは射程内の最初のスキルを返すこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
        ]
        context = SkillSelectionContext(
            usable_slot_indices={0, 1},
            targets_in_range_by_slot={},
        )
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result == 0

    def test_select_slot_usable_and_targets_combined(self, policy, actor, target_in_range):
        """usable_slot_indices と targets_in_range_by_slot を両方渡したとき、使用可能かつAOE優先で選ぶこと"""
        skills = [
            MonsterSkillInfo(slot_index=0, range=5, mp_cost=10),
            MonsterSkillInfo(slot_index=1, range=5, mp_cost=20),
            MonsterSkillInfo(slot_index=2, range=5, mp_cost=30),
        ]
        context = SkillSelectionContext(
            usable_slot_indices={0, 2},
            targets_in_range_by_slot={0: 1, 1: 5, 2: 3},
        )
        result = policy.select_slot(actor, target_in_range, skills, context)
        assert result == 2
