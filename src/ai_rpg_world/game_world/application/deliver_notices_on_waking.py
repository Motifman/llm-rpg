from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.deliver_perception import DeliverPerception, DeliverPerceptionCommand
from ai_rpg_world.game_world.application.deliver_surroundings import DeliverSurroundings, DeliverSurroundingsCommand
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.application.world_store import WorldSession
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.perception import BodilyStimulus, Notable
from ai_rpg_world.game_world.domain.perception.perception_outcome import Perceived
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class DeliverNoticesOnWakingCommand:
    person: PersonId
    at: WorldTick


@final
class DeliverNoticesOnWaking:
    def __init__(
        self,
        scope: CommandScope,
        design: WorldDesign,
        deliver_perception: DeliverPerception,
        deliver_surroundings: DeliverSurroundings,
        exit: ObservationExit,
    ) -> None:
        self._scope = scope
        self._design = design
        self._deliver_perception = deliver_perception
        self._deliver_surroundings = deliver_surroundings
        self._exit = exit

    def __call__(self, command: DeliverNoticesOnWakingCommand) -> None:
        waking = BodilyStimulus(
            person=command.person,
            text=self._design.surroundings_texts.waking.about({}),
            salience=Notable(),
            at=command.at,
        )
        self._deliver_perception(DeliverPerceptionCommand(from_actions=(waking,), from_states=()))
        for perceived in self._scope.run(lambda session: _missed_notices_taken(session, command)):
            self._exit.hand_over(perceived)
        self._deliver_surroundings(DeliverSurroundingsCommand(person=command.person, at=command.at))


def _missed_notices_taken(session: WorldSession, command: DeliverNoticesOnWakingCommand) -> tuple[Perceived, ...]:
    missed = session.aggregates().missed_notices(command.person)
    perceived = missed.perceived_on_waking(command.at)
    missed.clear()
    return perceived
