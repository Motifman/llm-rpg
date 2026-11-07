from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.world_id_exception import BlankWorldIdException


@final
@dataclass(frozen=True)
class WorldId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise BlankWorldIdException(f"WorldId must be non-blank, got {self.value!r}")
