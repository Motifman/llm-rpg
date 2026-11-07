from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.people_exception import (
    EmptyAppearanceException,
    EmptyVisibleNameException,
)
from ai_rpg_world.game_world.domain.people.person_handle import PersonHandle


@final
@dataclass(frozen=True)
class NoVisibleName:
    pass


@final
@dataclass(frozen=True)
class PersonRef:
    handle: PersonHandle
    appearance: str
    visible_name: str | NoVisibleName

    def __post_init__(self) -> None:
        if not self.appearance.strip():
            raise EmptyAppearanceException(f"PersonRef {self.handle.value} has no appearance")
        if isinstance(self.visible_name, str) and not self.visible_name.strip():
            raise EmptyVisibleNameException(f"PersonRef {self.handle.value} has a blank visible_name")


@final
@dataclass(frozen=True)
class Unidentified:
    pass
