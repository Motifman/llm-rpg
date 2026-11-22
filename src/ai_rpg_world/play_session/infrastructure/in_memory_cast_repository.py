from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy

from ai_rpg_world.game_world.domain.value_object import WorldId
from ai_rpg_world.play_session.domain.cast import BeingCastInWorldEvent, Cast, CastRepository
from ai_rpg_world.play_session.domain.play_session_exception import CastNotFoundException


class InMemoryCastRepository(CastRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。

    保存した配役がためたイベントは ``handoff`` に渡す。
    """

    def __init__(self, *, handoff: Callable[[Sequence[BeingCastInWorldEvent]], None] | None = None) -> None:
        self._by_world: dict[WorldId, Cast] = {}
        self._handoff = handoff

    def get(self, world: WorldId) -> Cast:
        if world not in self._by_world:
            raise CastNotFoundException(f"no cast for {world.value}")
        return deepcopy(self._by_world[world])

    def save(self, cast: Cast) -> None:
        events = cast.get_events()
        cast.clear_events()
        self._by_world[cast.world] = deepcopy(cast)
        if self._handoff is not None:
            self._handoff(events)
