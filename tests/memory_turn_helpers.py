"""記憶のターン数を固定で返す MemoryTurnReader。観測のターン数を気にしない試験で使う。"""

from __future__ import annotations

from collections.abc import Mapping

from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class FixedMemoryTurnReader(MemoryTurnReader):
    """Being ごとの値を渡せば Being ごとに、渡さなければ全員に ``turn`` を返す。"""

    def __init__(self, turn: int = 0, *, by_being: Mapping[BeingId, int] | None = None) -> None:
        self._turn = turn
        self._by_being = dict(by_being or {})

    def current_turn(self, being_id: BeingId) -> int:
        return self._by_being.get(being_id, self._turn)


ZERO_TURN = FixedMemoryTurnReader(0)

__all__ = ["FixedMemoryTurnReader", "ZERO_TURN"]
