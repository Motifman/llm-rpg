from dataclasses import dataclass

from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterTemplateValidationException


@dataclass(frozen=True)
class GrowthStage:
    """
    成長段階を表す値オブジェクト。
    after_ticks: スポーンからこのティック経過後にこの段階になる（この値以上でこの段階が適用される）
    stats_multiplier: 攻撃・防御・速度などに掛ける乗率（0.01〜2.0）
    """

    after_ticks: int
    stats_multiplier: float

    def __post_init__(self):
        if self.after_ticks < 0:
            raise MonsterTemplateValidationException(
                f"growth_stage.after_ticks cannot be negative: {self.after_ticks}"
            )
        if not (0.01 <= self.stats_multiplier <= 2.0):
            raise MonsterTemplateValidationException(
                f"growth_stage.stats_multiplier must be between 0.01 and 2.0: {self.stats_multiplier}"
            )
