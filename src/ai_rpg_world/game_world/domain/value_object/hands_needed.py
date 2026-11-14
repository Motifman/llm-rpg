from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least

HANDS_OF_A_PERSON = 2


@dataclass(frozen=True)
class HandsNeeded:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("HandsNeeded", self.value, 1)
        if self.value > HANDS_OF_A_PERSON:
            raise ValueOutOfRangeException(f"HandsNeeded must be 1 to {HANDS_OF_A_PERSON}, got {self.value}")
