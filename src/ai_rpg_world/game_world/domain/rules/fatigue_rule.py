from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.rules._level_ladder import require_level_ladder, require_level_name
from ai_rpg_world.game_world.domain.value_object import FatigueAmount


@dataclass(frozen=True)
class FatigueLevelName:
    value: str

    def __post_init__(self) -> None:
        require_level_name("FatigueLevelName", self.value)


@dataclass(frozen=True)
class FatigueLevel:
    starts_at: FatigueAmount
    name: FatigueLevelName


@dataclass(frozen=True)
class FatigueRule:
    per_exertion: FatigueAmount
    limit: FatigueAmount
    levels: tuple[FatigueLevel, ...]

    def __post_init__(self) -> None:
        require_level_ladder(
            "FatigueRule",
            [level.starts_at.value for level in self.levels],
            [level.name.value for level in self.levels],
            self.limit.value,
        )

    def level_of(self, amount: FatigueAmount) -> FatigueLevel:
        return next(level for level in reversed(self.levels) if level.starts_at <= amount)
