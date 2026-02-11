from dataclasses import dataclass
from enum import Enum

from ai_rpg_world.domain.combat.exception.combat_exceptions import HitEffectValidationException


class HitEffectType(Enum):
    """攻撃ヒット時に付与される追加効果の種類"""
    KNOCKBACK = "knockback"
    SLOW = "slow"
    POISON = "poison"
    PARALYSIS = "paralysis"
    SILENCE = "silence"


@dataclass(frozen=True)
class HitEffect:
    """
    ヒット時追加効果を表す値オブジェクト。
    intensity の意味は effect_type ごとに解釈する。
    """
    effect_type: HitEffectType
    duration_ticks: int
    intensity: float = 1.0
    chance: float = 1.0

    def __post_init__(self):
        if self.duration_ticks < 0:
            raise HitEffectValidationException(
                f"duration_ticks cannot be negative: {self.duration_ticks}"
            )
        if self.intensity < 0:
            raise HitEffectValidationException(
                f"intensity cannot be negative: {self.intensity}"
            )
        if self.chance < 0 or self.chance > 1:
            raise HitEffectValidationException(
                f"chance must be between 0 and 1: {self.chance}"
            )

        # 継続効果は少なくとも1ティック必要
        if (
            self.effect_type in {
                HitEffectType.SLOW,
                HitEffectType.POISON,
                HitEffectType.PARALYSIS,
                HitEffectType.SILENCE,
            }
            and self.duration_ticks == 0
        ):
            raise HitEffectValidationException(
                f"{self.effect_type.value} requires duration_ticks >= 1"
            )

    @classmethod
    def knockback(cls, cells: int, chance: float = 1.0) -> "HitEffect":
        return cls(
            effect_type=HitEffectType.KNOCKBACK,
            duration_ticks=0,
            intensity=float(cells),
            chance=chance,
        )

    @classmethod
    def slow(cls, rate: float, duration_ticks: int, chance: float = 1.0) -> "HitEffect":
        return cls(
            effect_type=HitEffectType.SLOW,
            duration_ticks=duration_ticks,
            intensity=rate,
            chance=chance,
        )

    @classmethod
    def poison(
        cls, damage_per_tick: float, duration_ticks: int, chance: float = 1.0
    ) -> "HitEffect":
        return cls(
            effect_type=HitEffectType.POISON,
            duration_ticks=duration_ticks,
            intensity=damage_per_tick,
            chance=chance,
        )

    @classmethod
    def paralysis(cls, duration_ticks: int, chance: float = 1.0) -> "HitEffect":
        return cls(
            effect_type=HitEffectType.PARALYSIS,
            duration_ticks=duration_ticks,
            intensity=1.0,
            chance=chance,
        )

    @classmethod
    def silence(cls, duration_ticks: int, chance: float = 1.0) -> "HitEffect":
        return cls(
            effect_type=HitEffectType.SILENCE,
            duration_ticks=duration_ticks,
            intensity=1.0,
            chance=chance,
        )
