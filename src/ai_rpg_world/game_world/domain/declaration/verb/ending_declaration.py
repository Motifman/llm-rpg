from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.condition.condition import Condition


@final
@dataclass(frozen=True)
class EndingDeclaration:
    ends_when: Condition

    def has_deadline(self) -> bool:
        return self.ends_when.requirements().reads_world_tick
