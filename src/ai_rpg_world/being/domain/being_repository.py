from __future__ import annotations

from typing import Protocol

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_id import BeingId


class BeingRepository(Protocol):
    def get(self, being_id: BeingId) -> Being:
        """いなければ ``BeingNotFoundException`` で断る。"""
        ...

    def save(self, being: Being) -> None: ...

    def add_if_absent(self, being: Being) -> None:
        """同じ ``BeingId`` の Being がもういれば、何も変えない。同じ ID ならもういる Being と同じ主体で、人柄は Being が世界をまたいで持つため (D1928-3)。"""
        ...


__all__ = ["BeingRepository"]
