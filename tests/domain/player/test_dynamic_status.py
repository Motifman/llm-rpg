import pytest

from domain.player.dynamic_status import DynamicStatus
from domain.player.enum import StatusEffectType


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

    def test_status_effect_add_remove_and_bonus_damage(self):
        status = DynamicStatus(hp=5, mp=1, max_hp=5, max_mp=1)
        status.add_status_effect(StatusEffectType.ATTACK_UP, duration=3, value=5)
        assert status.has_status_effect_type(StatusEffectType.ATTACK_UP) is True
        assert status.get_effect_bonus(StatusEffectType.ATTACK_UP) == 5
        assert status.get_effect_damage(StatusEffectType.ATTACK_UP) == 5
        status.remove_status_effect_by_type(StatusEffectType.ATTACK_UP)
        assert status.has_status_effect_type(StatusEffectType.ATTACK_UP) is False
        assert status.get_effect_bonus(StatusEffectType.ATTACK_UP) == 0

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


