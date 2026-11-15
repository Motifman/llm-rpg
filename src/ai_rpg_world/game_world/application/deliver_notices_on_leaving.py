from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
from ai_rpg_world.game_world.domain.person import Outcome
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class DeliverNoticesOnLeavingCommand:
    person: PersonId
    outcome: Outcome
    at: WorldTick


@final
class DeliverNoticesOnLeaving:
    def __init__(self, scope: CommandScope, exit: ObservationExit) -> None:
        self._scope = scope
        self._exit = exit

    def __call__(self, command: DeliverNoticesOnLeavingCommand) -> None:
        for perceived in self._scope.run(lambda session: _missed_notices_taken(session, command)):
            self._exit.hand_over(perceived)


def _missed_notices_taken(session: WorldSession, command: DeliverNoticesOnLeavingCommand) -> tuple[Perceived, ...]:
    missed = session.aggregates().missed_notices(command.person)
    perceived = command.outcome.notices_on_leaving(missed, command.at)
    command.outcome.forget_notices_on_leaving(missed)
    return perceived
