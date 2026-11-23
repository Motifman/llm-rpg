"""Being のターンを終わらせる。短期記憶が、範囲が埋まったか、いきさつが遅れているか、上限に届いたかを見る (#1824、design_decisions D1824-21)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository


@dataclass(frozen=True)
class EndBeingTurnCommand:
    being_id: BeingId


class EndBeingTurn:
    """起きたことは短期記憶がドメインイベントとしてため、保存するときに配送器に渡る。"""

    def __init__(self, store: ShortTermMemoryRepository, turn_reader: MemoryTurnReader) -> None:
        self._store = store
        self._turn_reader = turn_reader

    def execute(self, command: EndBeingTurnCommand) -> None:
        memory = self._store.get(command.being_id)
        memory.end_turn(turn=self._turn_reader.current_turn(command.being_id))
        self._store.save(memory)


__all__ = ["EndBeingTurn", "EndBeingTurnCommand"]
