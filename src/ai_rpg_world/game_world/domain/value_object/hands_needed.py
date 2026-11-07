from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True)
class HandsNeeded:
    """品物を手に持つのに要る手の数。人の手は 2 本なので 1 か 2。"""

    value: int

    def __post_init__(self) -> None:
        require_int_at_least("HandsNeeded", self.value, 1)
        if self.value > 2:
            raise ValueOutOfRangeException(f"HandsNeeded must be 1 or 2, got {self.value}")
