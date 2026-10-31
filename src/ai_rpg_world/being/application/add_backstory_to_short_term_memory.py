"""書いたいきさつを、その Being の短期記憶に入れて保存する (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemoryRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class AddBackstoryToShortTermMemoryCommand:
    being_id: BeingId
    backstory: Backstory


class AddBackstoryToShortTermMemory:
    """同じか前の範囲までのいきさつは、短期記憶が ``ShortTermMemoryStaleBackstoryException`` で断り、何も保存しない。"""

    def __init__(self, store: ShortTermMemoryRepository) -> None:
        self._store = store

    def execute(self, command: AddBackstoryToShortTermMemoryCommand) -> None:
        memory = self._store.get(command.being_id)
        memory.add_backstory(command.backstory)
        self._store.save(memory)


__all__ = ["AddBackstoryToShortTermMemory", "AddBackstoryToShortTermMemoryCommand"]
