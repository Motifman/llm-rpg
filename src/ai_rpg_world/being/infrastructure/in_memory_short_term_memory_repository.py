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


def _copy(memory: ShortTermMemory) -> ShortTermMemory:
    """出来事やいきさつは中身の変わらない値なので、同じものを持つ新しい集約を作れば写しになる。ためたイベントは写さない。"""
    return ShortTermMemory(
        memory.being_id,
        experiences=memory.experiences,
        backstories=memory.backstories,
        recent_from=memory.recent_from,
        awaiting=memory.awaiting,
    )


class InMemoryShortTermMemoryRepository(ShortTermMemoryRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self) -> None:
        self._by_being: dict[BeingId, ShortTermMemory] = {}

    def get(self, being_id: BeingId) -> ShortTermMemory:
        stored = self._by_being.get(being_id)
        return ShortTermMemory.empty(being_id) if stored is None else _copy(stored)

    def save(self, memory: ShortTermMemory) -> None:
        self._by_being[memory.being_id] = _copy(_require_memory(memory))

    def replace_all_by_being(self, memory: ShortTermMemory) -> None:
        if _require_memory(memory).is_empty():
            self._by_being.pop(memory.being_id, None)
            return
        self.save(memory)


__all__ = ["InMemoryShortTermMemoryRepository"]
