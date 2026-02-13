from dataclasses import dataclass
from typing import Optional, Tuple

from ai_rpg_world.domain.combat.value_object.hit_effect import HitEffect
from ai_rpg_world.domain.player.enum.player_enum import Element, Race
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillSpecValidationException
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId


@dataclass(frozen=True)
class SkillSpec:
    skill_id: SkillId
    name: str
    element: Element
    deck_cost: int
    cast_lock_ticks: int
    cooldown_ticks: int
    power_multiplier: float
    hit_pattern: SkillHitPattern
    mp_cost: Optional[int] = None
    stamina_cost: Optional[int] = None
    hp_cost: Optional[int] = None
    slayer_races: Tuple[Race, ...] = ()
    hit_effects: Tuple[HitEffect, ...] = ()
    required_skill_ids: Tuple[SkillId, ...] = ()
    is_awakened_deck_only: bool = False
    targeting_range: int = 1

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise SkillSpecValidationException("Skill name cannot be empty")
        if self.deck_cost < 0:
            raise SkillSpecValidationException(f"deck_cost cannot be negative: {self.deck_cost}")
        if self.cast_lock_ticks < 0:
            raise SkillSpecValidationException(
                f"cast_lock_ticks cannot be negative: {self.cast_lock_ticks}"
            )
        if self.cooldown_ticks < 0:
            raise SkillSpecValidationException(
                f"cooldown_ticks cannot be negative: {self.cooldown_ticks}"
            )
        if self.power_multiplier <= 0:
            raise SkillSpecValidationException(
                f"power_multiplier must be greater than 0: {self.power_multiplier}"
            )
        if self.targeting_range < 0:
            raise SkillSpecValidationException(
                f"targeting_range cannot be negative: {self.targeting_range}"
            )

        self._validate_optional_cost("mp_cost", self.mp_cost)
        self._validate_optional_cost("stamina_cost", self.stamina_cost)
        self._validate_optional_cost("hp_cost", self.hp_cost)

    @staticmethod
    def _validate_optional_cost(name: str, value: Optional[int]) -> None:
        if value is None:
            return
        if value < 0:
            raise SkillSpecValidationException(f"{name} cannot be negative: {value}")

    @property
    def has_resource_cost(self) -> bool:
        return any(v is not None and v > 0 for v in (self.mp_cost, self.stamina_cost, self.hp_cost))

