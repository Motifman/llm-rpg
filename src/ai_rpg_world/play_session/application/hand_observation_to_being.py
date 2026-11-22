from __future__ import annotations

from typing import final

from ai_rpg_world.being.application.perceive_observation import PerceiveObservation, PerceiveObservationCommand
from ai_rpg_world.being.contract import Observation
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.cast import CastRepository


@final
class HandObservationToBeing:
    def __init__(self, world: WorldId, casts: CastRepository, perceive: PerceiveObservation) -> None:
        self._world = world
        self._casts = casts
        self._perceive = perceive

    def receive(self, person: PersonId, observation: Observation) -> None:
        being_id = self._casts.get(self._world).being_of(person)
        self._perceive.execute(PerceiveObservationCommand(being_id=being_id, observation=observation))
