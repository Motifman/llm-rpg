import pytest
from ai_rpg_world.domain.monster.value_object.monster_hp import MonsterHp
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterStatsValidationException

class TestMonsterHp:
    """MonsterHp値オブジェクトのテスト"""

    def test_create_success(self):
        """有効な値でHPを作成できること"""
        hp = MonsterHp.create(80, 100)
        assert hp.value == 80
        assert hp.max_hp == 100

    def test_create_clamped(self):
        """最大値や最小値を超えた場合、範囲内に収められること"""
        # 最大値を超えた場合
        hp = MonsterHp.create(120, 100)
        assert hp.value == 100
        # 0を下回った場合
        hp2 = MonsterHp.create(-10, 100)
        assert hp2.value == 0

    def test_create_fail_negative_max(self):
        """最大HPに負の値を指定するとエラーが発生すること"""
        with pytest.raises(MonsterStatsValidationException):
            MonsterHp(0, -1)

    def test_damage(self):
        """ダメージを受けてHPが正しく減少すること"""
        hp = MonsterHp.create(100, 100)
        hp = hp.damage(30)
        assert hp.value == 70
        # 0未満にはならないこと
        hp = hp.damage(100)
        assert hp.value == 0

    def test_damage_negative_amount_raises_error(self):
        """負のダメージを与えようとするとエラーが発生すること"""
        hp = MonsterHp.create(100, 100)
        with pytest.raises(MonsterStatsValidationException):
            hp.damage(-10)

    def test_heal(self):
        """回復してHPが正しく増加すること"""
        hp = MonsterHp.create(50, 100)
        hp = hp.heal(30)
        assert hp.value == 80
        # 最大HPを超えないこと
        hp = hp.heal(50)
        assert hp.value == 100

    def test_heal_negative_amount_raises_error(self):
        """負の回復量を指定するとエラーが発生すること"""
        hp = MonsterHp.create(100, 100)
        with pytest.raises(MonsterStatsValidationException):
            hp.heal(-10)

    def test_is_alive(self):
        """生存判定が正しく行われること"""
        assert MonsterHp.create(1, 100).is_alive() is True
        assert MonsterHp.create(0, 100).is_alive() is False

    def test_get_percentage(self):
        """HPの割合が正しく取得できること"""
        hp = MonsterHp.create(50, 100)
        assert hp.get_percentage() == 0.5
        # 最大HPが0の場合（エッジケース）
        assert MonsterHp.create(0, 0).get_percentage() == 0.0
