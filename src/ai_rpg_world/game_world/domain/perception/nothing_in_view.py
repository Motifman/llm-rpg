from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.being.contract import Scene

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ai_rpg_world.game_world.domain.action.unavailable_object_operation import UnavailableObjectOperation
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SurroundingsTexts
    from ai_rpg_world.game_world.domain.declaration.time_and_weather.clock_wording import ClockWording
    from ai_rpg_world.game_world.domain.declaration.world_words import WorldWords
    from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
    from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
    from ai_rpg_world.game_world.domain.perception.surroundings import NamesInScene
    from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class NothingInView:
    def perceived_by(self, viewer: PersonId, texts: SurroundingsTexts, at: WorldTick) -> tuple[Perceived, ...]:
        return ()

    def scene_with(
        self,
        texts: SurroundingsTexts,
        names: NamesInScene,
        words: WorldWords,
        clock: ClockWording,
        unavailable: Sequence[UnavailableObjectOperation],
        view: PeopleAsSeen,
    ) -> Scene:
        return Scene()
