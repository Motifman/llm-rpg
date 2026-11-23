from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class MarkBodyAsShownCommand:
    person: PersonId


@final
class MarkBodyAsShown:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: MarkBodyAsShownCommand) -> None:
        self._scope.run(lambda session: session.aggregates().vitals(command.person).note_shown())
