from __future__ import annotations

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.being_repository import BeingRepository
from ai_rpg_world.domain.being.exception.being_exceptions import BeingNotFoundException


def _copy(being: Being) -> Being:
    return Being(being.being_id, being.persona, being.attachment)


class InMemoryBeingRepository(BeingRepository):
    """出し入れのたびに写しを渡す。同じ集約を指し続けると、save し忘れた書き換えも保存されたように見えるため。"""

    def __init__(self) -> None:
        self._by_id: dict[BeingId, Being] = {}

    def get(self, being_id: BeingId) -> Being:
        if being_id not in self._by_id:
            raise BeingNotFoundException(f"Being({being_id}) is not prepared")
        return _copy(self._by_id[being_id])

    def save(self, being: Being) -> None:
        self._by_id[being.being_id] = _copy(being)

    def add_if_absent(self, being: Being) -> None:
        self._by_id.setdefault(being.being_id, _copy(being))


__all__ = ["InMemoryBeingRepository"]
