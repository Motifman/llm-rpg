from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.action_exception import BlankRefusalCodeException
from ai_rpg_world.game_world.domain.exception.game_world_exception import GameWorldDomainException


@final
@dataclass(frozen=True)
class RefusalCode:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.strip():
            raise BlankRefusalCodeException(f"RefusalCode must be non-blank, got {self.value!r}")

    @classmethod
    def of(cls, exception: GameWorldDomainException) -> RefusalCode:
        return cls(exception.error_code)
