"""書いたいきさつを、その Being の短期記憶に入れて保存する (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai_rpg_world.being.domain.short_term_memory import Backstory, ShortTermMemoryRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class AddBackstoryToShortTermMemoryCommand:
    """``truncated`` は、書いたときに上限を超えて切り詰めた項目と切り詰める前の長さ。"""

    being_id: BeingId
    backstory: Backstory
    truncated: dict[str, int] = field(default_factory=dict)


class AddBackstoryToShortTermMemory:
    """同じか前の範囲までのいきさつは、短期記憶が ``ShortTermMemoryStaleBackstoryException`` で断り、何も保存しない。"""

    def __init__(self, store: ShortTermMemoryRepository) -> None:
        self._store = store

    def execute(self, command: AddBackstoryToShortTermMemoryCommand) -> None:
        memory = self._store.get(command.being_id)
        memory.add_backstory(command.backstory, truncated=command.truncated)
        self._store.save(memory)


__all__ = ["AddBackstoryToShortTermMemory", "AddBackstoryToShortTermMemoryCommand"]
