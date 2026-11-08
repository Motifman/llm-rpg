from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class Weight:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("Weight", self.value, 1)
