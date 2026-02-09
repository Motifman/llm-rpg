import pytest
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateIdValidationException

class TestMonsterTemplateId:
    """MonsterTemplateId値オブジェクトのテスト"""

    def test_create_success(self):
        """有効な数値でMonsterTemplateIdを作成できること"""
        template_id = MonsterTemplateId.create(1)
        assert template_id.value == 1

    def test_create_fail_with_negative_value(self):
        """負の数値でMonsterTemplateIdを作成しようとするとエラーが発生すること"""
        with pytest.raises(MonsterTemplateIdValidationException):
            MonsterTemplateId.create(-1)

    def test_equality(self):
        """同じ値を持つMonsterTemplateId同士が等価と判定されること"""
        id1 = MonsterTemplateId.create(1)
        id2 = MonsterTemplateId.create(1)
        id3 = MonsterTemplateId.create(2)
        assert id1 == id2
        assert id1 != id3
