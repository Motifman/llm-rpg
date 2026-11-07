from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least
from ai_rpg_world.game_world.domain.value_object.damage import Damage
from ai_rpg_world.game_world.domain.value_object.heal_amount import HealAmount


@dataclass(frozen=True)
class HitPoints:
    """体力の今の値と最大値。最大値は、起こすときの割合 (ReviveEffect.hp_rate) の基準になる。"""

    current: int
    maximum: int

    def __post_init__(self) -> None:
        require_int_at_least("HitPoints.current", self.current, 0)
        require_int_at_least("HitPoints.maximum", self.maximum, 1)
        if self.current > self.maximum:
            raise ValueOutOfRangeException(f"HitPoints.current {self.current} exceeds maximum {self.maximum}")

    def damaged_by(self, damage: Damage) -> HitPoints:
        return HitPoints(current=max(0, self.current - damage.value), maximum=self.maximum)

    def healed_by(self, heal: HealAmount) -> HitPoints:
        return HitPoints(current=min(self.maximum, self.current + heal.value), maximum=self.maximum)
