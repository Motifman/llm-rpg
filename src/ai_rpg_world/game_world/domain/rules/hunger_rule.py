from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.rules._level_ladder import require_level_ladder, require_level_name
from ai_rpg_world.game_world.domain.value_object import Damage, HungerAmount


@dataclass(frozen=True)
class HungerLevelName:
    value: str

    def __post_init__(self) -> None:
        require_level_name("HungerLevelName", self.value)


@dataclass(frozen=True)
class HungerLevel:
    starts_at: HungerAmount
    name: HungerLevelName


@dataclass(frozen=True)
class NoStarvationDamage:
    pass


@dataclass(frozen=True)
class HungerRule:
    per_tick: HungerAmount
    limit: HungerAmount
    starvation_damage: Damage | NoStarvationDamage
    levels: tuple[HungerLevel, ...]

    def __post_init__(self) -> None:
        require_level_ladder(
            "HungerRule",
            [level.starts_at.value for level in self.levels],
            [level.name.value for level in self.levels],
            self.limit.value,
        )

    def level_of(self, amount: HungerAmount) -> HungerLevel:
        return next(level for level in reversed(self.levels) if level.starts_at <= amount)
