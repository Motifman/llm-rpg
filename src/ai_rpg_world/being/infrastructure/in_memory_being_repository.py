from __future__ import annotations

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.being_repository import BeingRepository


def _copy(being: Being) -> Being:
    return Being(being.being_id, being.persona, being.attachment)


class InMemoryBeingRepository(BeingRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self) -> None:
        self._by_id: dict[BeingId, Being] = {}

    def find_by_id(self, being_id: BeingId) -> Being | None:
        stored = self._by_id.get(being_id)
        return None if stored is None else _copy(stored)

    def save(self, being: Being) -> None:
        self._by_id[being.being_id] = _copy(being)


__all__ = ["InMemoryBeingRepository"]
