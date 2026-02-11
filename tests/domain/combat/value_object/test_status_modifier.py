import pytest
from ai_rpg_world.domain.combat.value_object.status_modifier import StatusModifier, ModifierType, StatTarget
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats

class TestStatusModifier:
    def test_apply_additive_modifier(self):
        # Given
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=50, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        # 攻撃力 +10
        mod = StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=10.0)
        
        # When
        new_stats = stats.apply_modifiers([mod])
        
        # Then
        assert new_stats.attack == 60
        assert new_stats.max_hp == 100 # 他は変わらない

    def test_apply_multiplicative_modifier(self):
        # Given
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=50, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        # 攻撃力 1.5倍
        mod = StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=1.5)
        
        # When
        new_stats = stats.apply_modifiers([mod])
        
        # Then
        assert new_stats.attack == 75

    def test_apply_mixed_modifiers(self):
        # Given
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=50, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        # (攻撃力 +10) * 1.5倍 = 60 * 1.5 = 90
        mods = [
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=10.0),
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=1.5)
        ]
        
        # When
        new_stats = stats.apply_modifiers(mods)
        
        # Then
        assert new_stats.attack == 90

    def test_apply_multiple_multiplicative_modifiers(self):
        # Given
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=100, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        # 0.8倍 * 0.5倍 = 0.4倍
        mods = [
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=0.8),
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=0.5)
        ]
        
        # When
        new_stats = stats.apply_modifiers(mods)
        
        # Then
        assert new_stats.attack == 40

    def test_rate_modifiers_clamping(self):
        # Given
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=50, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        # クリティカル率 +1.0 (100%) -> 1.0 にクランプされる
        mods = [
            StatusModifier(target=StatTarget.CRITICAL_RATE, modifier_type=ModifierType.ADDITIVE, value=1.0)
        ]
        
        # When
        new_stats = stats.apply_modifiers(mods)
        
        # Then
        assert new_stats.critical_rate == 1.0

    def test_negative_result_clamping(self):
        # Given
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=50, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        # 攻撃力 -100 -> 0 にクランプされる
        mods = [
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=-100.0)
        ]
        
        # When
        new_stats = stats.apply_modifiers(mods)
        
        # Then
        assert new_stats.attack == 0
