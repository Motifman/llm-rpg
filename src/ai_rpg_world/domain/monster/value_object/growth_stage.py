from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException

# 成長段階の最大数（テンプレートで定義可能な段階数の上限）
MAX_GROWTH_STAGES = 4


@dataclass(frozen=True)
class GrowthStage:
    """
    成長段階を表す値オブジェクト。
    after_ticks: スポーンからこのティック経過後にこの段階になる（この値以上でこの段階が適用される）。最初の段階は 0 とする。
    stats_multiplier: 攻撃・防御・速度・max_hp・max_mp に掛ける乗率（0.01〜2.0）
    flee_bias_multiplier: FLEE 閾値に掛ける乗率（未指定時は 1.0）。1.0 より大きいと逃げやすく（閾値が実質上がる）、小さいと逃げにくい
    allow_chase: この段階で CHASE（追跡）してよいか。幼体などは False
    """

    after_ticks: int
    stats_multiplier: float
    flee_bias_multiplier: Optional[float] = None
    allow_chase: bool = True

    def __post_init__(self):
        if self.after_ticks < 0:
            raise MonsterTemplateValidationException(
                f"growth_stage.after_ticks cannot be negative: {self.after_ticks}"
            )
        if not (0.01 <= self.stats_multiplier <= 2.0):
            raise MonsterTemplateValidationException(
                f"growth_stage.stats_multiplier must be between 0.01 and 2.0: {self.stats_multiplier}"
            )
        if self.flee_bias_multiplier is not None and not (0.1 <= self.flee_bias_multiplier <= 3.0):
            raise MonsterTemplateValidationException(
                f"growth_stage.flee_bias_multiplier must be between 0.1 and 3.0: {self.flee_bias_multiplier}"
            )
