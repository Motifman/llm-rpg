from __future__ import annotations

from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.lighting import Lighting, LightingConditions
from ai_rpg_world.game_world.domain.people.people_seen_by import PeopleSeenBy
from ai_rpg_world.game_world.domain.perception.scene_conditions import SceneConditions
from ai_rpg_world.game_world.domain.perception.surroundings import SpotContents
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
class SurroundingsInWorld:
    def __init__(self, viewer: PersonId, facts: WorldFacts, design: WorldDesign) -> None:
        self._viewer = viewer
        self._facts = facts
        self._design = design

    def lighting_at(self, spot: SpotId) -> Lighting:
        return LightingConditions.at(self._facts.nouns().spot_of(spot), self._facts).lighting()

    def conditions_at(self, spot: SpotId) -> SceneConditions:
        return SceneConditions.at(self._facts.nouns().spot_of(spot), self._facts, self.lighting_at(spot))

    def contents_at(self, spot: SpotId) -> SpotContents:
        return SpotContents.around(
            self._viewer,
            self._facts.nouns().spot_of(spot),
            self._facts,
            self._design,
            PeopleSeenBy.in_world(self._viewer, self._facts),
        )
