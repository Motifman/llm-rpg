from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.value_object.reaction_id import ReactionId


@final
@dataclass(frozen=True)
class ReactionDeclaration:
    reaction_id: ReactionId
    condition: Condition
    when_becomes_true: Effect
    when_becomes_false: Effect
