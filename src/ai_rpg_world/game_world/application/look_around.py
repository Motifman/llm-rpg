from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception.nothing_in_view import NothingInView
from ai_rpg_world.game_world.domain.perception.surroundings import VisibleSurroundings
from ai_rpg_world.game_world.domain.value_object import PersonId


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
        return VisibleSurroundings.seen_by_person(person, session.facts(), self._design)
