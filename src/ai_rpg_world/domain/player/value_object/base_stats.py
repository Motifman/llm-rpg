from dataclasses import dataclass
from typing import List, TYPE_CHECKING

from ai_rpg_world.domain.player.exception import BaseStatsValidationException
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.combat.value_object.status_modifier import ModifierType, StatTarget

if TYPE_CHECKING:
    from ai_rpg_world.domain.combat.value_object.status_modifier import StatusModifier


@dataclass(frozen=True)
class BaseStats:
    max_hp: int
    max_mp: int
    attack: int
    defense: int
    speed: int
    critical_rate: float
    evasion_rate: float

    def __post_init__(self):
        if self.max_hp < 0:
            raise BaseStatsValidationException(f"max_hp must be greater than 0. max_hp: {self.max_hp}")
        if self.max_mp < 0:
            raise BaseStatsValidationException(f"max_mp must be greater than 0. max_mp: {self.max_mp}")
        if self.attack < 0:
            raise BaseStatsValidationException(f"attack must be greater than 0. attack: {self.attack}")
        if self.defense < 0:
            raise BaseStatsValidationException(f"defense must be greater than 0. defense: {self.defense}")
        if self.speed < 0:
            raise BaseStatsValidationException(f"speed must be greater than 0. speed: {self.speed}")
        if self.critical_rate < 0.0 or self.critical_rate > 1.0:
            raise BaseStatsValidationException(f"critical_rate must be between 0.0 and 1.0. critical_rate: {self.critical_rate}")
        if self.evasion_rate < 0.0 or self.evasion_rate > 1.0:
            raise BaseStatsValidationException(f"evasion_rate must be between 0.0 and 1.0. evasion_rate: {self.evasion_rate}")
    
    def grow(self, growth_factor: StatGrowthFactor) -> 'BaseStats':
        """成長率に基づいてステータスを成長させた新しいBaseStatsを返す

        Args:
            growth_factor: 成長率を表すStatGrowthFactor

        Returns:
            BaseStats: 成長した新しいBaseStats
        """
        return BaseStats(
            max_hp=int(self.max_hp * (1.0 + growth_factor.hp_factor)),
            max_mp=int(self.max_mp * (1.0 + growth_factor.mp_factor)),
            attack=int(self.attack * (1.0 + growth_factor.attack_factor)),
            defense=int(self.defense * (1.0 + growth_factor.defense_factor)),
            speed=int(self.speed * (1.0 + growth_factor.speed_factor)),
            critical_rate=min(1.0, self.critical_rate + growth_factor.critical_rate_factor),
            evasion_rate=min(1.0, self.evasion_rate + growth_factor.evasion_rate_factor),
        )

    def apply_modifiers(self, modifiers: List['StatusModifier']) -> 'BaseStats':
        """ステータス補正を適用した新しいBaseStatsを返す
        
        計算順序: (基本値 + 加算補正の合計) * 乗算補正の積
        """
        # 各ステータスごとの補正を保持
        stats_map = {
            StatTarget.MAX_HP: {"base": float(self.max_hp), "add": 0.0, "mul": 1.0},
            StatTarget.MAX_MP: {"base": float(self.max_mp), "add": 0.0, "mul": 1.0},
            StatTarget.ATTACK: {"base": float(self.attack), "add": 0.0, "mul": 1.0},
            StatTarget.DEFENSE: {"base": float(self.defense), "add": 0.0, "mul": 1.0},
            StatTarget.SPEED: {"base": float(self.speed), "add": 0.0, "mul": 1.0},
            StatTarget.CRITICAL_RATE: {"base": self.critical_rate, "add": 0.0, "mul": 1.0},
            StatTarget.EVASION_RATE: {"base": self.evasion_rate, "add": 0.0, "mul": 1.0},
        }

        for mod in modifiers:
            if mod.target not in stats_map:
                continue
            
            if mod.modifier_type == ModifierType.ADDITIVE:
                stats_map[mod.target]["add"] += mod.value
            elif mod.modifier_type == ModifierType.MULTIPLICATIVE:
                stats_map[mod.target]["mul"] *= mod.value

        def calc(target: StatTarget, is_float: bool = False):
            data = stats_map[target]
            val = (data["base"] + data["add"]) * data["mul"]
            if is_float:
                return max(0.0, min(1.0, val))
            return max(0, int(val))

        return BaseStats(
            max_hp=calc(StatTarget.MAX_HP),
            max_mp=calc(StatTarget.MAX_MP),
            attack=calc(StatTarget.ATTACK),
            defense=calc(StatTarget.DEFENSE),
            speed=calc(StatTarget.SPEED),
            critical_rate=calc(StatTarget.CRITICAL_RATE, is_float=True),
            evasion_rate=calc(StatTarget.EVASION_RATE, is_float=True),
        )
