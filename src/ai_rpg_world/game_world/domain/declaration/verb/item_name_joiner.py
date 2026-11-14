from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.verb_declaration_exception import BlankItemNameJoinerException
from ai_rpg_world.game_world.domain.value_object import DisplayName


@final
@dataclass(frozen=True)
class ItemNameJoiner:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip() or self.text.splitlines() != [self.text]:
            raise BlankItemNameJoinerException(f"ItemNameJoiner must be a non-blank single line, got {self.text!r}")

    def join(self, names: tuple[DisplayName, ...]) -> DisplayName:
        return DisplayName(self.text.join(name.text for name in names))
