from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.application.look_around import LookAround, LookAroundCommand
from ai_rpg_world.game_world.application.observation_exit import ObservationExit
from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldTick


@final
@dataclass(frozen=True)
class DeliverSurroundingsCommand:
    person: PersonId
    at: WorldTick


@final
class DeliverSurroundings:
    def __init__(self, look_around: LookAround, design: WorldDesign, exit: ObservationExit) -> None:
        self._look_around = look_around
        self._design = design
        self._exit = exit

    def __call__(self, command: DeliverSurroundingsCommand) -> None:
        surroundings = self._look_around(LookAroundCommand(command.person))
        for perceived in surroundings.perceived_by(command.person, self._design.surroundings_texts, command.at):
            self._exit.hand_over(perceived)
