from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.effect.effect import Effect


@final
@dataclass(frozen=True)
class WorldStageEffectsDeclaration:
    stage: WorldStageDeclaration
    when_entered: Effect
    when_left: Effect
