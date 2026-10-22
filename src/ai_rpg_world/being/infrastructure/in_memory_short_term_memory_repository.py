from __future__ import annotations

from ai_rpg_world.being.domain.short_term_memory import (
    ShortTermMemory,
    ShortTermMemoryRepository,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


def _require_memory(memory: object) -> ShortTermMemory:
    if not isinstance(memory, ShortTermMemory):
        raise TypeError("memory must be ShortTermMemory")
    return memory


class InMemoryShortTermMemoryRepository(ShortTermMemoryRepository):
    def __init__(self) -> None:
        self._by_being: dict[BeingId, ShortTermMemory] = {}

    def get(self, being_id: BeingId) -> ShortTermMemory:
        return self._by_being.get(being_id, ShortTermMemory.empty())

    def save(self, being_id: BeingId, memory: ShortTermMemory) -> None:
        self._by_being[being_id] = _require_memory(memory)

    def replace_all_by_being(self, being_id: BeingId, memory: ShortTermMemory) -> None:
        if _require_memory(memory) == ShortTermMemory.empty():
            self._by_being.pop(being_id, None)
            return
        self._by_being[being_id] = memory


__all__ = ["InMemoryShortTermMemoryRepository"]
