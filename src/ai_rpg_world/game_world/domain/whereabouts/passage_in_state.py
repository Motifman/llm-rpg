from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration
from ai_rpg_world.game_world.domain.value_object import PassageStateName


@final
@dataclass(frozen=True)
class PassageInState:
    passage: PassageDeclaration
    state: PassageStateName

    def __post_init__(self) -> None:
        self.passage.state(self.state)
