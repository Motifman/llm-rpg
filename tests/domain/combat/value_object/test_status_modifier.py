import pytest

from ai_rpg_world.domain.combat.value_object.status_modifier import ModifierType, StatTarget, StatusModifier
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats


class TestStatusModifier:
    def test_apply_additive_modifier(self):
        # Given
        stats = BaseStats(max_hp=100, max_mp=50, attack=50, defense=30, speed=10, critical_rate=0.1, evasion_rate=0.05)
        # 攻撃力 +10
        mod = StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=10.0)

        # When
        new_stats = stats.apply_modifiers([mod])

        # Then
        assert new_stats.attack == 60
        assert new_stats.max_hp == 100  # 他は変わらない

    @pytest.mark.parametrize(
        ("stats", "mods", "expected"),
        [
            pytest.param(
                BaseStats(100, 50, 50, 30, 10, 0.1, 0.05),
                [
                    StatusModifier(StatTarget.ATTACK, ModifierType.MULTIPLICATIVE, 1.5),
                    StatusModifier(StatTarget.CRITICAL_RATE, ModifierType.ADDITIVE, 5.0),
                    StatusModifier(StatTarget.EVASION_RATE, ModifierType.ADDITIVE, -1.0),
                ],
                BaseStats(100, 50, 75, 30, 10, 1.0, 0.0),
                id="original_amount_types_and_rate_bounds",
            ),
            pytest.param(
                BaseStats(101, 51, 51, 31, 11, 0.1, 0.05),
                [
                    StatusModifier(StatTarget.MAX_HP, ModifierType.MULTIPLICATIVE, 1.5),
                    StatusModifier(StatTarget.MAX_MP, ModifierType.MULTIPLICATIVE, 1.5),
                    StatusModifier(StatTarget.ATTACK, ModifierType.MULTIPLICATIVE, 1.5),
                    StatusModifier(StatTarget.DEFENSE, ModifierType.MULTIPLICATIVE, 1.5),
                    StatusModifier(StatTarget.SPEED, ModifierType.MULTIPLICATIVE, 1.5),
                ],
                BaseStats(151, 76, 76, 46, 16, 0.1, 0.05),
                id="fractional_amounts_are_truncated",
            ),
        ],
    )
    def test_apply_modifiers_keeps_amounts_int_and_rates_in_range(self, stats, mods, expected):
        """補正後の量5種類は端数を切り捨てたintとなり、割合は0.0-1.0に収まる。"""
        new_stats = stats.apply_modifiers(mods)

        assert isinstance(new_stats.attack, int)
        assert isinstance(new_stats.max_hp, int)
        assert isinstance(new_stats.max_mp, int)
        assert isinstance(new_stats.defense, int)
        assert isinstance(new_stats.speed, int)
        assert new_stats == expected

    def test_apply_multiplicative_modifier(self):
        # Given
        stats = BaseStats(max_hp=100, max_mp=50, attack=50, defense=30, speed=10, critical_rate=0.1, evasion_rate=0.05)
        # 攻撃力 1.5倍
        mod = StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=1.5)

        # When
        new_stats = stats.apply_modifiers([mod])

        # Then
        assert new_stats.attack == 75

    def test_apply_mixed_modifiers(self):
        # Given
        stats = BaseStats(max_hp=100, max_mp=50, attack=50, defense=30, speed=10, critical_rate=0.1, evasion_rate=0.05)
        # (攻撃力 +10) * 1.5倍 = 60 * 1.5 = 90
        mods = [
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=10.0),
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=1.5),
        ]

        # When
        new_stats = stats.apply_modifiers(mods)

        # Then
        assert new_stats.attack == 90

    def test_apply_multiple_multiplicative_modifiers(self):
        # Given
        stats = BaseStats(max_hp=100, max_mp=50, attack=100, defense=30, speed=10, critical_rate=0.1, evasion_rate=0.05)
        # 0.8倍 * 0.5倍 = 0.4倍
        mods = [
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=0.8),
            StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=0.5),
        ]

        # When
        new_stats = stats.apply_modifiers(mods)

        # Then
        assert new_stats.attack == 40

    def test_rate_modifiers_clamping(self):
        # Given
        stats = BaseStats(max_hp=100, max_mp=50, attack=50, defense=30, speed=10, critical_rate=0.1, evasion_rate=0.05)
        # クリティカル率 +1.0 (100%) -> 1.0 にクランプされる
        mods = [StatusModifier(target=StatTarget.CRITICAL_RATE, modifier_type=ModifierType.ADDITIVE, value=1.0)]

        # When
        new_stats = stats.apply_modifiers(mods)

        # Then
        assert new_stats.critical_rate == 1.0

    def test_negative_result_clamping(self):
        # Given
        stats = BaseStats(max_hp=100, max_mp=50, attack=50, defense=30, speed=10, critical_rate=0.1, evasion_rate=0.05)
        # 攻撃力 -100 -> 0 にクランプされる
        mods = [StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=-100.0)]

        # When
        new_stats = stats.apply_modifiers(mods)

        # Then
        assert new_stats.attack == 0
