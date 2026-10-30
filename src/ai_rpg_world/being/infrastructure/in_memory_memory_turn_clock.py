from __future__ import annotations

from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnClock,
    require_memory_turn,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


def _require_being_id(being_id: object) -> BeingId:
    if not isinstance(being_id, BeingId):
        raise TypeError("being_id must be BeingId")
    return being_id


class InMemoryMemoryTurnClock(MemoryTurnClock):
    def __init__(self) -> None:
        self._turns: dict[BeingId, int] = {}

    def current_turn(self, being_id: BeingId) -> int:
        return self._turns.get(_require_being_id(being_id), 0)

    def advance_turn(self, being_id: BeingId) -> int:
        turn = self.current_turn(being_id) + 1
        self._turns[being_id] = turn
        return turn

    def replace_all_by_being(self, being_id: BeingId, *, turn: int) -> None:
        _require_being_id(being_id)
        restored = require_memory_turn(turn)
        if restored == 0:
            self._turns.pop(being_id, None)
        else:
            self._turns[being_id] = restored


__all__ = ["InMemoryMemoryTurnClock"]
