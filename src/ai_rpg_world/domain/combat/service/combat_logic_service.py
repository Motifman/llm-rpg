import random
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.combat.value_object.damage import Damage


from ai_rpg_world.domain.combat.service.combat_config_service import CombatConfigService, DefaultCombatConfigService


class CombatLogicService:
    """
    戦闘ロジック（ダメージ計算、回避判定など）を司るドメインサービス。
    プレイヤー、モンスターを問わず共通の計算式を適用する。
    """

    @staticmethod
    def calculate_damage(
        attacker_stats: BaseStats,
        defender_stats: BaseStats,
        power_multiplier: float = 1.0,
        config: CombatConfigService = DefaultCombatConfigService()
    ) -> Damage:
        """
        攻撃側と防御側のステータスを元に最終ダメージを計算する。
        """
        # 1. 回避判定
        if random.random() < defender_stats.evasion_rate:
            return Damage.evaded()

        # 2. クリティカル判定
        is_critical = False
        crit_multiplier = 1.0
        if random.random() < attacker_stats.critical_rate:
            is_critical = True
            crit_multiplier = config.get_critical_multiplier()

        # 3. ダメージ計算式 (攻撃力 - 防御力/2) * 倍率
        # 最低でも1ダメージは与える
        raw_damage = attacker_stats.attack - (defender_stats.defense / 2)
        final_value = int(max(config.get_minimum_damage(), raw_damage) * power_multiplier * crit_multiplier)

        return Damage.normal(value=final_value, is_critical=is_critical)
