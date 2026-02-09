import pytest
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterIdValidationException

class TestMonsterId:
    """MonsterId値オブジェクトのテスト"""

    def test_create_success(self):
        """有効な数値でMonsterIdを作成できること"""
        monster_id = MonsterId.create(1)
        assert monster_id.value == 1

    def test_create_fail_with_negative_value(self):
        """負の数値でMonsterIdを作成しようとするとエラーが発生すること"""
        with pytest.raises(MonsterIdValidationException):
            MonsterId.create(-1)

    def test_equality(self):
        """同じ値を持つMonsterId同士が等価と判定されること"""
        id1 = MonsterId.create(1)
        id2 = MonsterId.create(1)
        id3 = MonsterId.create(2)
        assert id1 == id2
        assert id1 != id3
