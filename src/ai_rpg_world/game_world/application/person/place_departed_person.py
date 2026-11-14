from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class PlaceDepartedPersonCommand:
    person: PersonId


@final
class PlaceDepartedPerson:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: PlaceDepartedPersonCommand) -> None:
        def work(session: WorldSession) -> None:
            departed_persons_act = session.facts().rules().departed_persons_act
            session.aggregates().whereabouts().place_departed(command.person, departed_persons_act)

        self._scope.run(work)
