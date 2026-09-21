import pytest

from ai_rpg_world.domain.combat.value_object.status_modifier import ModifierType, StatTarget, StatusModifier
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

    def test_apply_modifiers_keeps_amounts_int_and_rates_in_range(self):
        """補正の適用後も、量は int のまま、割合は 0.0-1.0 に収まる。

        補正の計算は float で行う。量 (max_hp など) は int へ丸め、割合
        (critical_rate / evasion_rate) は 0.0-1.0 に切り詰めるという 2 種類の
        扱いが 1 つの関数に真偽値引数で同居しており、戻り値の型が呼び出しに
        よって変わっていた。
        """
        stats = BaseStats(
            max_hp=100, max_mp=50, attack=50, defense=30, speed=10,
            critical_rate=0.1, evasion_rate=0.05
        )
        mods = [
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=1.5),
            StatusModifier(target=StatTarget.CRITICAL_RATE, modifier_type=ModifierType.ADDITIVE, value=5.0),
            StatusModifier(target=StatTarget.EVASION_RATE, modifier_type=ModifierType.ADDITIVE, value=-1.0),
        ]

        new_stats = stats.apply_modifiers(mods)

        assert isinstance(new_stats.attack, int)
        assert isinstance(new_stats.max_hp, int)
        assert new_stats.critical_rate == 1.0
        assert new_stats.evasion_rate == 0.0

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
