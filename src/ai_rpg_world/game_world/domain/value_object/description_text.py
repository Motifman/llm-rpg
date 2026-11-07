from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.display_text_exception import BlankDescriptionTextException


@final
@dataclass(frozen=True)
class DescriptionText:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise BlankDescriptionTextException(f"DescriptionText must be non-blank, got {self.text!r}")
