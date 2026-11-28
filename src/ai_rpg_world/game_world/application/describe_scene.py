from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import Scene
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception.names_in_world import NamesInWorld
from ai_rpg_world.game_world.domain.perception.oneself import Oneself
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class DescribeSceneCommand:
    person: PersonId


@final
class DescribeScene:
    def __init__(self, scope: CommandScope, design: WorldDesign) -> None:
        self._scope = scope
        self._design = design

    def __call__(self, command: DescribeSceneCommand) -> Scene:
        return self._scope.run(lambda session: self._describe(session, command.person))

    def _describe(self, session: WorldSession, person: PersonId) -> Scene:
        facts = session.facts()
        seen = VisibleSurroundings.seen_by_person(person, facts, self._design)
        return seen.scene_with(
            self._design.surroundings_texts,
            NamesInWorld(facts),
            self._design.world_words,
            self._design.clock_wording,
            Oneself.of(person, facts),
        )
