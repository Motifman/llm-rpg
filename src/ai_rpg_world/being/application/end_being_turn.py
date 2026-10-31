"""Being のターンを終わらせる。短期記憶が、範囲が埋まったか、いきさつが遅れているか、上限に届いたかを見る (#1824、design_decisions D1824-21)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class EndBeingTurnCommand:
    """``turn`` は終わったターン (Being の記憶のターン数)。"""

    being_id: BeingId
    turn: int


class EndBeingTurn:
    """起きたことは短期記憶がドメインイベントとしてため、保存するときに配送器に渡る。"""

    def __init__(self, store: ShortTermMemoryRepository) -> None:
        self._store = store

    def execute(self, command: EndBeingTurnCommand) -> None:
        memory = self._store.get(command.being_id)
        memory.end_turn(turn=command.turn)
        self._store.save(memory)


__all__ = ["EndBeingTurn", "EndBeingTurnCommand"]
