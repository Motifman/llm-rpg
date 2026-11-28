from __future__ import annotations

from typing import final

from ai_rpg_world.being.application.perceive_observation import PerceiveObservation, PerceiveObservationCommand
from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.play_session.domain.cast import CastRepository
from ai_rpg_world.play_session.domain.turn_rounds import ObservationPassedOnEvent


@final
class PassObservationToBeingHandler(EventHandler[ObservationPassedOnEvent]):
    def __init__(self, casts: CastRepository, perceive: PerceiveObservation) -> None:
        self._casts = casts
        self._perceive = perceive

    def handle(self, event: ObservationPassedOnEvent) -> None:
        being_id = self._casts.get(event.world).being_of(event.person)
        self._perceive.execute(PerceiveObservationCommand(being_id=being_id, observation=event.observation))
