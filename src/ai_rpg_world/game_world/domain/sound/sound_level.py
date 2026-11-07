from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class SoundLoss:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("SoundLoss", self.value, 0)

    def plus(self, other: SoundLoss) -> SoundLoss:
        return SoundLoss(self.value + other.value)


@final
@dataclass(frozen=True)
class SoundLevel:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("SoundLevel", self.value, 0)

    def weakened_by(self, loss: SoundLoss) -> SoundLevel:
        return SoundLevel(max(0, self.value - loss.value))

    def is_below(self, other: SoundLevel) -> bool:
        return self.value < other.value
