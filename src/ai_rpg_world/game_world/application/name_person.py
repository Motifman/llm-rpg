from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId


@final
@dataclass(frozen=True)
class NamePersonCommand:
    person: PersonId
    name: DisplayName


@final
class NamePerson:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: NamePersonCommand) -> None:
        self._scope.run(lambda session: session.people_register().name(command.person, command.name))
