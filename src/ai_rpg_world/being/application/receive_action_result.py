from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.contract import Observation
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.being.domain.short_term_memory import ObservedOutcome, ShortTermMemoryRepository


@dataclass(frozen=True)
class ReceiveActionResultCommand:
    """``result`` は、経路が自分の行動の結果 (``OwnActionResult``) の観測。"""

    being_id: BeingId
    result: Observation


class ReceiveActionResult:
    def __init__(self, short_term_memories: ShortTermMemoryRepository, turn_reader: MemoryTurnReader) -> None:
        self._short_term_memories = short_term_memories
        self._turn_reader = turn_reader

    def execute(self, command: ReceiveActionResultCommand) -> None:
        memory = self._short_term_memories.get(command.being_id)
        # 呼び名は受け取ったときのもので埋める。観測と同じく、あとで名前を知っても結果の記憶は書き換えない
        memory.receive_result(
            ObservedOutcome(command.result.with_people_named(text_naming_people)),
            current_turn=self._turn_reader.current_turn(command.being_id),
        )
        self._short_term_memories.save(memory)


__all__ = ["ReceiveActionResult", "ReceiveActionResultCommand"]
