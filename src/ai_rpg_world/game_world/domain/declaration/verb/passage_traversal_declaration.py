from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.declaration.spot import PassageDeclaration


@final
@dataclass(frozen=True)
class PassageTraversalDeclaration:
    passage: PassageDeclaration
    condition: Condition
