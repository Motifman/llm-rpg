from __future__ import annotations

from typing import final

from ai_rpg_world.being.contract import Observation
from ai_rpg_world.game_world.domain.value_object import PersonId, WorldId
from ai_rpg_world.play_session.domain.turn_rounds import TurnRoundsRepository


@final
class HandObservationToBeing:
    def __init__(self, world: WorldId, turn_rounds: TurnRoundsRepository) -> None:
        self._world = world
        self._turn_rounds = turn_rounds

    def receive(self, person: PersonId, observation: Observation) -> None:
        rounds = self._turn_rounds.get(self._world)
        rounds.notice_observation(person, observation)
        self._turn_rounds.save(rounds)
