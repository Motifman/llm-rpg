from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SurroundingsTexts
    from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
    from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class NothingInView:
    def perceived_by(self, viewer: PersonId, texts: SurroundingsTexts, at: WorldTick) -> tuple[Perceived, ...]:
        return ()
