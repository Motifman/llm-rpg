import pytest

from src.domain.player.dynamic_status import DynamicStatus
from src.domain.battle.battle_enum import StatusEffectType


@pytest.mark.unit
class TestDynamicStatus:
    def test_init_validations(self):
        with pytest.raises(AssertionError):
            DynamicStatus(hp=0, mp=1, max_hp=1, max_mp=1)
        with pytest.raises(AssertionError):
            DynamicStatus(hp=1, mp=0, max_hp=1, max_mp=1)
        with pytest.raises(AssertionError):
            DynamicStatus(hp=1, mp=1, max_hp=0, max_mp=1)
        with pytest.raises(AssertionError):
            DynamicStatus(hp=1, mp=1, max_hp=1, max_mp=0)
        # exp, level, gold: boundary
        DynamicStatus(hp=1, mp=1, max_hp=1, max_mp=1, exp=0, level=1, gold=0)

    def test_take_damage_and_heal_cap(self):
        status = DynamicStatus(hp=10, mp=5, max_hp=10, max_mp=5)
        status.take_damage(3)
        assert status.hp == 7
        status.take_damage(100)
        assert status.hp == 0
        status.heal(3)
        assert status.hp == 3
        status.heal(100)
        assert status.hp == 10

    def test_is_alive(self):
        status = DynamicStatus(hp=5, mp=1, max_hp=5, max_mp=1)
        assert status.is_alive() is True
        status.take_damage(5)
        assert status.is_alive() is False

    def test_gold_and_exp_never_negative(self):
        status = DynamicStatus(hp=5, mp=1, max_hp=5, max_mp=1, exp=10, gold=10)
        status.receive_gold(-5)
        assert status.gold == 5
        status.receive_gold(-100)
        assert status.gold == 0
        status.receive_exp(-3)
        assert status.exp == 7
        status.receive_exp(-100)
        assert status.exp == 0

    def test_defend_flags(self):
        status = DynamicStatus(hp=5, mp=1, max_hp=5, max_mp=1)
        assert status.defending is False
        status.defend()
        assert status.defending is True
        status.un_defend()
        assert status.defending is False

    def test_decrease_status_effect_duration_and_removal(self):
        status = DynamicStatus(hp=5, mp=1, max_hp=5, max_mp=1)
        status.add_status_effect(StatusEffectType.POISON, duration=1, value=2)
        status.add_status_effect(StatusEffectType.BLESSING, duration=2, value=3)
        status.decrease_status_effect_duration()
        # poison removed, blessing remains with duration=1
        assert status.has_status_effect_type(StatusEffectType.POISON) is False
        assert status.has_status_effect_type(StatusEffectType.BLESSING) is True
        status.decrease_status_effect_duration()
        # blessing removed
        assert status.has_status_effect_type(StatusEffectType.BLESSING) is False

    def test_recover_mp_with_max_cap(self):
        """MP回復のテスト（最大値でキャップされる）"""
        status = DynamicStatus(hp=10, mp=3, max_hp=10, max_mp=10)
        
        # 通常の回復
        status.recover_mp(2)
        assert status.mp == 5
        
        # 最大値を超える回復（キャップされる）
        status.recover_mp(10)
        assert status.mp == 10
    
    def test_consume_mp(self):
        """MP消費のテスト"""
        status = DynamicStatus(hp=10, mp=10, max_hp=10, max_mp=10)
        
        # 通常の消費
        status.consume_mp(3)
        assert status.mp == 7
        
        # MPが足りる場合の消費
        status.consume_mp(5)
        assert status.mp == 2
        
        # MPが足りない場合の消費（0でキャップされる）
        status.consume_mp(5)
        assert status.mp == 0
    
    def test_consume_mp_invalid_amount(self):
        """MP消費で無効な値を指定した場合のエラーテスト"""
        status = DynamicStatus(hp=10, mp=10, max_hp=10, max_mp=10)
        
        with pytest.raises(AssertionError, match="amount must be greater than 0"):
            status.consume_mp(0)
        
        with pytest.raises(AssertionError, match="amount must be greater than 0"):
            status.consume_mp(-1)
    
    def test_can_consume_mp(self):
        """MP消費可能かどうかのテスト"""
        status = DynamicStatus(hp=10, mp=5, max_hp=10, max_mp=10)
        
        # 十分なMPがある場合
        assert status.can_consume_mp(3) is True
        assert status.can_consume_mp(5) is True
        
        # MPが足りない場合
        assert status.can_consume_mp(6) is False
        assert status.can_consume_mp(10) is False
        
        # 境界値テスト
        assert status.can_consume_mp(0) is True  # 0は常にTrue
        
        # MP消費後のテスト
        status.consume_mp(3)
        assert status.mp == 2
        assert status.can_consume_mp(2) is True
        assert status.can_consume_mp(3) is False


