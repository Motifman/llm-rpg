from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import InvalidSpotIdException


@dataclass(frozen=True)
class SpotId:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise InvalidSpotIdException(f"SpotId must be a non-blank declared name, got {self.value!r}")
