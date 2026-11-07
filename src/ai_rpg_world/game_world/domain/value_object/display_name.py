from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.display_text_exception import (
    BlankDisplayNameException,
    MultilineDisplayNameException,
)


@final
@dataclass(frozen=True)
class DisplayName:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankDisplayNameException(f"DisplayName must be non-blank, got {self.text!r}")
        if self.text.splitlines() != [self.text]:
            raise MultilineDisplayNameException(f"DisplayName must be a single line, got {self.text!r}")
