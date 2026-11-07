from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.design_flaw.design_location import DesignLocation


@final
@dataclass(frozen=True)
class DesignFlaw:
    location: DesignLocation
    reason: str

    def __str__(self) -> str:
        return f"{self.location}: {self.reason}"
