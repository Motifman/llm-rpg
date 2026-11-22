from __future__ import annotations

from typing import final

from ai_rpg_world.being.application.perceive_observation import PerceiveObservation, PerceiveObservationCommand
from ai_rpg_world.being.contract import Observation
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.cast import CastRepository
from ai_rpg_world.play_session.domain.turn_rounds import TurnRoundsRepository


@final
class HandObservationToBeing:
    def __init__(
        self, world: WorldId, casts: CastRepository, turn_rounds: TurnRoundsRepository, perceive: PerceiveObservation
    ) -> None:
        self._world = world
        self._casts = casts
        self._turn_rounds = turn_rounds
        self._perceive = perceive

    def receive(self, person: PersonId, observation: Observation) -> None:
        being_id = self._casts.get(self._world).being_of(person)
        self._perceive.execute(PerceiveObservationCommand(being_id=being_id, observation=observation))
        rounds = self._turn_rounds.get(self._world)
        rounds.notice_observation(person, observation)
        self._turn_rounds.save(rounds)
