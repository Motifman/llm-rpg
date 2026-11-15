from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.domain.person import Died
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class DecideDeathOutcomeCommand:
    person: PersonId
    at: WorldTick


@final
class DecideDeathOutcome:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: DecideDeathOutcomeCommand) -> None:
        self._scope.run(lambda session: session.aggregates().outcomes().decide(command.person, Died(), command.at))
