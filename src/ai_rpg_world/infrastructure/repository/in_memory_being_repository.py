"""InMemoryBeingRepository — Being 集約のインメモリ実装。

Phase 2 PR1: Being 容器の最小骨格用 in-memory 実装。プロセス内 dict で保持。
SQLite 実装は後続 PR (Issue #469 checkpoint Stage 2 と統合予定) で追加する。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class InMemoryBeingRepository(BeingRepository):
    """プロセス内 dict で Being を保持する Repository。"""

    def __init__(self) -> None:
        self._store: dict[BeingId, Being] = {}

    def save(self, being: Being) -> None:
        if not isinstance(being, Being):
            raise TypeError(
                f"being must be Being, got {type(being).__name__}"
            )
        self._store[being.being_id] = being

    def find_by_id(self, being_id: BeingId) -> Being | None:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        return self._store.get(being_id)

    def exists(self, being_id: BeingId) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        return being_id in self._store

    def delete(self, being_id: BeingId) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        return self._store.pop(being_id, None) is not None


__all__ = ["InMemoryBeingRepository"]
