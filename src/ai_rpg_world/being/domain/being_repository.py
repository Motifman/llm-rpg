from __future__ import annotations

from typing import Protocol

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId


class BeingRepository(Protocol):
    def find_by_id(self, being_id: BeingId) -> Being | None: ...

    def save(self, being: Being) -> None: ...


__all__ = ["BeingRepository"]
