from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople


@final
@dataclass(frozen=True)
class NoticedOnWaking:
    text: TextWithUnassignedPeople

    def placeholders(self) -> frozenset[str]:
        return self.text.placeholders()
