from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import FatigueAmount, HitPoints, HungerAmount


@final
@dataclass(frozen=True)
class BodyChange:
    hp: int
    hunger: int
    fatigue: int


@final
@dataclass(frozen=True)
class ShownBody:
    hp: HitPoints
    hunger: HungerAmount
    fatigue: FatigueAmount

    def change_to(self, hp: HitPoints, hunger: HungerAmount, fatigue: FatigueAmount) -> BodyChange:
        return BodyChange(
            hp=hp.current - self.hp.current,
            hunger=hunger.value - self.hunger.value,
            fatigue=fatigue.value - self.fatigue.value,
        )


@final
@dataclass(frozen=True)
class NothingShownYet:
    def change_to(self, hp: HitPoints, hunger: HungerAmount, fatigue: FatigueAmount) -> BodyChange:
        return BodyChange(hp=0, hunger=0, fatigue=0)


LastShownBody = ShownBody | NothingShownYet
