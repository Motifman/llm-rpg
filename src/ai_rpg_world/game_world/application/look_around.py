from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_perception_senses import WorldPerceptionSenses, perceiver_of
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.lighting import Lighting
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import SpotContents, VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId


@final
@dataclass(frozen=True)
class LookAroundCommand:
    person: PersonId


@final
class LookAround:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: LookAroundCommand) -> VisibleSurroundings | NothingInView:
        return self._scope.run(lambda session: self._look(session, command.person))

    def _look(self, session: WorldSession, person: PersonId) -> VisibleSurroundings | NothingInView:
        facts = session.facts()
        return VisibleSurroundings.seen_by(perceiver_of(facts, person), SurroundingsOf(person, facts, self._design))


@final
class SurroundingsOf:
    def __init__(self, viewer: PersonId, facts: WorldFacts, design: WorldDesign) -> None:
        self._viewer = viewer
        self._facts = facts
        self._design = design
        self._senses = WorldPerceptionSenses(facts)

    def lighting_at(self, spot: SpotId) -> Lighting:
        return self._senses.lighting_at(spot)

    def contents_at(self, spot: SpotId) -> SpotContents:
        return SpotContents.around(
            self._viewer,
            self._facts.nouns().spot_of(spot),
            self._facts,
            self._design,
            self._senses.view_for(self._viewer),
        )
