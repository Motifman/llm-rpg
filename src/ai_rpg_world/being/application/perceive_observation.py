from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.names_for_people import text_naming_people
from ai_rpg_world.being.contract import Observation
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository


@dataclass(frozen=True)
class PerceiveObservationCommand:
    being_id: BeingId
    observation: Observation


class PerceiveObservation:
    def __init__(self, short_term_memories: ShortTermMemoryRepository, turn_reader: MemoryTurnReader) -> None:
        self._short_term_memories = short_term_memories
        self._turn_reader = turn_reader

    def execute(self, command: PerceiveObservationCommand) -> None:
        memory = self._short_term_memories.get(command.being_id)
        # 呼び名は受け取ったときのものにする。あとで名前を知っても、そのとき知覚したとおりに覚えておくため
        memory.perceive(
            command.observation.with_people_named(text_naming_people),
            current_turn=self._turn_reader.current_turn(command.being_id),
        )
        self._short_term_memories.save(memory)


__all__ = ["PerceiveObservation", "PerceiveObservationCommand"]
