"""MonsterSkillInfo 値オブジェクトのテスト"""

import pytest

from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo


class TestMonsterSkillInfoCreation:
    """MonsterSkillInfo の生成テスト（正常・境界）"""

    def test_create_with_required_fields(self):
        """必須フィールドで作成できること"""
        info = MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)
        assert info.slot_index == 0
        assert info.range == 5
        assert info.mp_cost == 10

    def test_create_boundary_slot_index_zero(self):
        """slot_index=0 が境界として有効であること"""
        info = MonsterSkillInfo(slot_index=0, range=1, mp_cost=0)
        assert info.slot_index == 0
        assert info.range == 1
        assert info.mp_cost == 0

    def test_create_large_values(self):
        """大きな range / mp_cost で作成できること"""
        info = MonsterSkillInfo(slot_index=3, range=999, mp_cost=100)
        assert info.slot_index == 3
        assert info.range == 999
        assert info.mp_cost == 100

    def test_equality_by_value(self):
        """同じ値なら等価であること"""
        a = MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)
        b = MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)
        assert a == b
        assert hash(a) == hash(b)

    def test_inequality_different_values(self):
        """異なる値なら等価でないこと"""
        a = MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)
        b = MonsterSkillInfo(slot_index=1, range=5, mp_cost=10)
        assert a != b
        assert a != MonsterSkillInfo(slot_index=0, range=6, mp_cost=10)
        assert a != MonsterSkillInfo(slot_index=0, range=5, mp_cost=11)


class TestMonsterSkillInfoImmutability:
    """不変性の検証"""

    def test_info_is_frozen(self):
        """MonsterSkillInfo は frozen で属性代入できないこと"""
        info = MonsterSkillInfo(slot_index=0, range=5, mp_cost=10)
        with pytest.raises(AttributeError):
            info.slot_index = 1  # type: ignore[misc]
        with pytest.raises(AttributeError):
            info.range = 10  # type: ignore[misc]
        with pytest.raises(AttributeError):
            info.mp_cost = 20  # type: ignore[misc]
