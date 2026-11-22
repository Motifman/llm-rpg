from __future__ import annotations

from dataclasses import dataclass

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
        memory.perceive(command.observation, current_turn=self._turn_reader.current_turn(command.being_id))
        self._short_term_memories.save(memory)


__all__ = ["PerceiveObservation", "PerceiveObservationCommand"]
