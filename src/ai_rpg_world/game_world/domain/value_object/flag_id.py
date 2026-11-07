from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object._checks import require_declared_name


@final
@dataclass(frozen=True)
class FlagId:
    value: str

    def __post_init__(self) -> None:
        require_declared_name("FlagId", self.value)
