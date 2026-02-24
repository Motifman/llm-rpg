"""EffectiveStatsDomainService（compute_effective_stats）のユニットテスト"""
import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.common.service.effective_stats_domain_service import (
    compute_effective_stats,
)
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.combat.value_object.status_effect import StatusEffect
from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType


def _base_stats(attack: int = 20, defense: int = 10, speed: int = 5) -> BaseStats:
    return BaseStats(
        max_hp=100,
        max_mp=50,
        attack=attack,
        defense=defense,
        speed=speed,
        critical_rate=0.0,
        evasion_rate=0.0,
    )


class TestComputeEffectiveStats:
    """compute_effective_stats のテスト"""

    def test_no_effects_returns_base_unchanged(self):
        base = _base_stats(attack=20)
        result = compute_effective_stats(base, [], WorldTick(10))
        assert result.attack == 20
        assert result.defense == 10
        assert result.max_hp == 100

    def test_multiple_buffs_multiply(self):
        base = _base_stats(attack=20)
        effects = [
            StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)),
            StatusEffect(StatusEffectType.ATTACK_UP, 1.2, WorldTick(100)),
        ]
        result = compute_effective_stats(base, effects, WorldTick(10))
        assert result.attack == 36  # 20 * 1.5 * 1.2

    def test_filters_expired_effects(self):
        base = _base_stats(attack=20)
        effects = [
            StatusEffect(StatusEffectType.ATTACK_UP, 2.0, WorldTick(5)),
            StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(20)),
        ]
        result = compute_effective_stats(base, effects, WorldTick(10))
        assert result.attack == 30  # 20 * 1.5 only

    def test_buff_and_debuff_stacking(self):
        base = _base_stats(attack=20)
        effects = [
            StatusEffect(StatusEffectType.ATTACK_UP, 1.5, WorldTick(100)),
            StatusEffect(StatusEffectType.ATTACK_DOWN, 0.5, WorldTick(100)),
        ]
        result = compute_effective_stats(base, effects, WorldTick(10))
        assert result.attack == 15  # 20 * 1.5 * 0.5

    def test_defense_and_speed_effects(self):
        base = _base_stats(attack=10, defense=20, speed=8)
        effects = [
            StatusEffect(StatusEffectType.DEFENSE_UP, 1.5, WorldTick(100)),
            StatusEffect(StatusEffectType.SPEED_DOWN, 0.5, WorldTick(100)),
        ]
        result = compute_effective_stats(base, effects, WorldTick(10))
        assert result.attack == 10
        assert result.defense == 30  # 20 * 1.5
        assert result.speed == 4  # 8 * 0.5

    def test_max_hp_mp_and_rates_unchanged(self):
        base = BaseStats(
            max_hp=200,
            max_mp=80,
            attack=15,
            defense=12,
            speed=7,
            critical_rate=0.25,
            evasion_rate=0.1,
        )
        effects = [
            StatusEffect(StatusEffectType.ATTACK_UP, 2.0, WorldTick(100)),
        ]
        result = compute_effective_stats(base, effects, WorldTick(10))
        assert result.max_hp == 200
        assert result.max_mp == 80
        assert result.critical_rate == 0.25
        assert result.evasion_rate == 0.1
        assert result.attack == 30
