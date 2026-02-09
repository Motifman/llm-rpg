import pytest
from ai_rpg_world.domain.monster.value_object.monster_mp import MonsterMp
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterStatsValidationException,
    MonsterInsufficientMpException
)

class TestMonsterMp:
    """MonsterMp値オブジェクトのテスト"""

    def test_create_success(self):
        """有効な値でMPを作成できること"""
        mp = MonsterMp.create(40, 50)
        assert mp.value == 40
        assert mp.max_mp == 50

    def test_create_clamped(self):
        """最大値や最小値を超えた場合、範囲内に収められること"""
        # 最大値を超えた場合
        mp = MonsterMp.create(60, 50)
        assert mp.value == 50
        # 0を下回った場合
        mp2 = MonsterMp.create(-5, 50)
        assert mp2.value == 0

    def test_use_mp_success(self):
        """MPを消費して正しく減少すること"""
        mp = MonsterMp.create(50, 50)
        mp = mp.use(20)
        assert mp.value == 30

    def test_use_mp_fail_insufficient(self):
        """MPが不足している場合に消費しようとするとエラーが発生すること"""
        mp = MonsterMp.create(10, 50)
        with pytest.raises(MonsterInsufficientMpException, match="Insufficient MP"):
            mp.use(20)

    def test_recover_mp(self):
        """MPが回復して正しく増加すること"""
        mp = MonsterMp.create(10, 50)
        mp = mp.recover(20)
        assert mp.value == 30
        # 最大値を超えないこと
        mp = mp.recover(50)
        assert mp.value == 50
