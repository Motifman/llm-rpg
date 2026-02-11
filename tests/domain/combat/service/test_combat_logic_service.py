from unittest.mock import patch

import pytest

from ai_rpg_world.domain.combat.service.combat_logic_service import CombatLogicService
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats


class TestCombatLogicService:
    @pytest.fixture
    def attacker_stats(self) -> BaseStats:
        return BaseStats(
            max_hp=100,
            max_mp=50,
            attack=50,
            defense=20,
            speed=10,
            critical_rate=0.0,
            evasion_rate=0.0,
        )

    @pytest.fixture
    def defender_stats(self) -> BaseStats:
        return BaseStats(
            max_hp=100,
            max_mp=50,
            attack=20,
            defense=30,
            speed=10,
            critical_rate=0.0,
            evasion_rate=0.0,
        )

    class TestCalculateDamage:
        def test_calculate_damage_normal(self, attacker_stats: BaseStats, defender_stats: BaseStats):
            # Damage = (50 - 30/2) * 1.0 = 35
            damage = CombatLogicService.calculate_damage(attacker_stats, defender_stats)
            assert damage.value == 35
            assert damage.is_evaded is False
            assert damage.is_critical is False

        def test_calculate_damage_evaded(self, attacker_stats: BaseStats):
            evasive_defender = BaseStats(
                max_hp=100,
                max_mp=50,
                attack=20,
                defense=30,
                speed=10,
                critical_rate=0.0,
                evasion_rate=1.0,
            )
            damage = CombatLogicService.calculate_damage(attacker_stats, evasive_defender)
            assert damage.is_evaded is True
            assert damage.value == 0

        def test_calculate_damage_critical(self, defender_stats: BaseStats):
            critical_attacker = BaseStats(
                max_hp=100,
                max_mp=50,
                attack=50,
                defense=20,
                speed=10,
                critical_rate=1.0,
                evasion_rate=0.0,
            )
            # Damage = (50 - 30/2) * 1.5 = 35 * 1.5 = 52.5 -> int(52)
            damage = CombatLogicService.calculate_damage(critical_attacker, defender_stats)
            assert damage.is_critical is True
            assert damage.value == 52

        def test_calculate_damage_minimum_damage_guarantee(self, attacker_stats: BaseStats):
            tank_defender = BaseStats(
                max_hp=100,
                max_mp=50,
                attack=20,
                defense=200,
                speed=10,
                critical_rate=0.0,
                evasion_rate=0.0,
            )
            damage = CombatLogicService.calculate_damage(attacker_stats, tank_defender)
            assert damage.value == 1
            assert damage.is_evaded is False

        def test_calculate_damage_applies_power_multiplier(self, attacker_stats: BaseStats, defender_stats: BaseStats):
            damage = CombatLogicService.calculate_damage(attacker_stats, defender_stats, power_multiplier=2.0)
            assert damage.value == 70

        def test_calculate_damage_with_custom_config(self, attacker_stats: BaseStats, defender_stats: BaseStats):
            from ai_rpg_world.domain.combat.service.combat_config_service import DefaultCombatConfigService
            # Critical multiplier = 2.0, Minimum damage = 10
            config = DefaultCombatConfigService(critical_multiplier=2.0, minimum_damage=10)
            
            # Normal with minimum damage
            tank_defender = BaseStats(
                max_hp=100, max_mp=50, attack=20, defense=200, speed=10, critical_rate=0.0, evasion_rate=0.0
            )
            damage = CombatLogicService.calculate_damage(attacker_stats, tank_defender, config=config)
            assert damage.value == 10
            
            # Critical with custom multiplier
            critical_attacker = BaseStats(
                max_hp=100, max_mp=50, attack=50, defense=20, speed=10, critical_rate=1.0, evasion_rate=0.0
            )
            # Damage = (50 - 30/2) * 2.0 = 35 * 2 = 70
            damage = CombatLogicService.calculate_damage(critical_attacker, defender_stats, config=config)
            assert damage.value == 70

        def test_calculate_damage_evasion_has_priority_over_critical(self, attacker_stats: BaseStats, defender_stats: BaseStats):
            attacker = BaseStats(
                max_hp=attacker_stats.max_hp,
                max_mp=attacker_stats.max_mp,
                attack=attacker_stats.attack,
                defense=attacker_stats.defense,
                speed=attacker_stats.speed,
                critical_rate=1.0,
                evasion_rate=attacker_stats.evasion_rate,
            )
            defender = BaseStats(
                max_hp=defender_stats.max_hp,
                max_mp=defender_stats.max_mp,
                attack=defender_stats.attack,
                defense=defender_stats.defense,
                speed=defender_stats.speed,
                critical_rate=defender_stats.critical_rate,
                evasion_rate=1.0,
            )
            with patch("random.random", return_value=0.0):
                damage = CombatLogicService.calculate_damage(attacker, defender)
            assert damage.is_evaded is True
            assert damage.is_critical is False
            assert damage.value == 0

        def test_calculate_damage_with_applied_modifiers(self, attacker_stats: BaseStats, defender_stats: BaseStats):
            from ai_rpg_world.domain.combat.value_object.status_modifier import StatusModifier, ModifierType, StatTarget
            
            # 攻撃力バフ適用: (50 + 10) * 1.2 = 72
            buffs = [
                StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.ADDITIVE, value=10.0),
                StatusModifier(target=StatTarget.ATTACK, modifier_type=ModifierType.MULTIPLICATIVE, value=1.2)
            ]
            effective_attacker = attacker_stats.apply_modifiers(buffs)
            
            # ダメージ = (72 - 30/2) * 1.0 = 57
            damage = CombatLogicService.calculate_damage(effective_attacker, defender_stats)
            assert damage.value == 57
