from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.application.leave_environment import LeaveEnvironment, LeaveEnvironmentCommand
from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.play_session.domain.cast import CastRepository


@final
@dataclass(frozen=True)
class EndPlaySessionCommand:
    world: WorldId


@final
class EndPlaySession:
    def __init__(self, *, casts: CastRepository, leave_environment: LeaveEnvironment) -> None:
        self._casts = casts
        self._leave_environment = leave_environment

    def __call__(self, command: EndPlaySessionCommand) -> None:
        cast = self._casts.get(command.world)
        for person in cast.people():
            self._leave_environment.execute(LeaveEnvironmentCommand(cast.being_of(person)))
