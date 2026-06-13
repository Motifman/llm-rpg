"""InMemoryBeingRepository — Being 集約のインメモリ実装。

Phase 2 PR1: Being 容器の最小骨格用 in-memory 実装。プロセス内 dict で保持。
SQLite 実装は後続 PR (Issue #469 checkpoint Stage 2 と統合予定) で追加する。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


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

    def find_all_attached_to(
        self, world_id: WorldId, player_id: PlayerId
    ) -> list[Being]:
        if not isinstance(world_id, WorldId):
            raise TypeError(
                f"world_id must be WorldId, got {type(world_id).__name__}"
            )
        if not isinstance(player_id, PlayerId):
            raise TypeError(
                f"player_id must be PlayerId, got {type(player_id).__name__}"
            )
        return [
            being
            for being in self._store.values()
            if being.attachment is not None
            and being.attachment.world_id == world_id
            and being.attachment.player_id == player_id
        ]


__all__ = ["InMemoryBeingRepository"]
