from dataclasses import dataclass
from ai_rpg_world.domain.player.exception import BaseStatsValidationException
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor


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