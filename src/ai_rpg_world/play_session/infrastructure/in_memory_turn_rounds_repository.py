from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy

from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.play_session.domain.play_session_exception import TurnRoundsNotFoundException
from ai_rpg_world.play_session.domain.turn_rounds import TurnRounds, TurnRoundsEvent, TurnRoundsRepository


class InMemoryTurnRoundsRepository(TurnRoundsRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self, *, handoff: Callable[[Sequence[TurnRoundsEvent]], None] | None = None) -> None:
        self._by_world: dict[WorldId, TurnRounds] = {}
        self._handoff = handoff

    def get(self, world: WorldId) -> TurnRounds:
        if world not in self._by_world:
            raise TurnRoundsNotFoundException(f"no turn rounds for {world.value}")
        return deepcopy(self._by_world[world])

    def save(self, rounds: TurnRounds) -> None:
        events = rounds.get_events()
        rounds.clear_events()
        self._by_world[rounds.world] = deepcopy(rounds)
        if self._handoff is not None:
            self._handoff(events)
