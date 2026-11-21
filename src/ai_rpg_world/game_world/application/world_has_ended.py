from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope


@final
@dataclass(frozen=True)
class WorldHasEndedCommand:
    pass


@final
class WorldHasEnded:
    def __init__(self, scope: CommandScope) -> None:
        self._scope = scope

    def __call__(self, command: WorldHasEndedCommand) -> bool:
        return self._scope.run(lambda session: session.ending().has_ended())
