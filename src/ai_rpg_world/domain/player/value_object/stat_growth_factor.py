from dataclasses import dataclass
import math
from ai_rpg_world.domain.player.exception import StatGrowthFactorValidationException


@dataclass(frozen=True)
class StatGrowthFactor:
    """BaseStatsの成長率を表すバリューオブジェクト

    各ステータスの成長率を持ち、レベルに応じた成長率を計算する。
    レベルの上昇に対して成長率は緩やかに減少していく。
    """
    hp_factor: float
    mp_factor: float
    attack_factor: float
    defense_factor: float
    speed_factor: float
    critical_rate_factor: float
    evasion_rate_factor: float

    def __post_init__(self):
        if self.hp_factor < 0:
            raise StatGrowthFactorValidationException(f"hp_factor must be greater than or equal to 0. hp_factor: {self.hp_factor}")
        if self.mp_factor < 0:
            raise StatGrowthFactorValidationException(f"mp_factor must be greater than or equal to 0. mp_factor: {self.mp_factor}")
        if self.attack_factor < 0:
            raise StatGrowthFactorValidationException(f"attack_factor must be greater than or equal to 0. attack_factor: {self.attack_factor}")
        if self.defense_factor < 0:
            raise StatGrowthFactorValidationException(f"defense_factor must be greater than or equal to 0. defense_factor: {self.defense_factor}")
        if self.speed_factor < 0:
            raise StatGrowthFactorValidationException(f"speed_factor must be greater than or equal to 0. speed_factor: {self.speed_factor}")
        if self.critical_rate_factor < 0:
            raise StatGrowthFactorValidationException(f"critical_rate_factor must be greater than or equal to 0. critical_rate_factor: {self.critical_rate_factor}")
        if self.evasion_rate_factor < 0:
            raise StatGrowthFactorValidationException(f"evasion_rate_factor must be greater than or equal to 0. evasion_rate_factor: {self.evasion_rate_factor}")

    @staticmethod
    def for_level(level: int, base_growth_rate: float = 1.0) -> 'StatGrowthFactor':
        """レベルに応じた成長率を計算してStatGrowthFactorを返す

        レベルの上昇に対して成長率は緩やかに減少していく。
        成長率 = base_growth_rate / sqrt(level)

        Args:
            level: 現在のレベル
            base_growth_rate: 基本成長率

        Returns:
            StatGrowthFactor: 計算された成長率
        """
        if level <= 0:
            raise StatGrowthFactorValidationException(f"level must be greater than 0. level: {level}")

        # レベルの上昇に対して成長率が緩やかに減少
        growth_multiplier = base_growth_rate / math.sqrt(level)

        return StatGrowthFactor(
            hp_factor=growth_multiplier,
            mp_factor=growth_multiplier,
            attack_factor=growth_multiplier,
            defense_factor=growth_multiplier,
            speed_factor=growth_multiplier,
            critical_rate_factor=growth_multiplier * 0.1,  # クリティカル率は成長しにくい
            evasion_rate_factor=growth_multiplier * 0.1,   # 回避率も成長しにくい
        )
