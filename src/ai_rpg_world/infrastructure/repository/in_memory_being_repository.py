"""InMemoryBeingRepository — Being 集約のインメモリ実装。

Phase 2 PR1: Being 容器の最小骨格用 in-memory 実装。プロセス内 dict で保持。
SQLite 実装は後続 PR (Issue #469 checkpoint Stage 2 と統合予定) で追加する。
"""

from __future__ import annotations

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_snapshot_codec import (
    BeingSnapshotCodec,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class InMemoryBeingRepository(BeingRepository):
    """プロセス内 dict で Being を保持する Repository。

    Phase 4 Step 4-3: ``BeingSnapshot`` を内部 source of truth に格上げ。
    aggregate を返す ``find_by_id`` は ``BeingSnapshotCodec`` 経由で構築する。
    これにより ``save_snapshot`` (= payload 付き snapshot) も同じ store に
    乗る。
    """

    def __init__(self) -> None:
        self._snapshots: dict[BeingId, BeingSnapshot] = {}

    def save(self, being: Being) -> None:
        if not isinstance(being, Being):
            raise TypeError(
                f"being must be Being, got {type(being).__name__}"
            )
        # codec で encode して内部 snapshot store に統一。payload なし v2。
        self._snapshots[being.being_id] = BeingSnapshotCodec.encode(being)

    def save_snapshot(self, snapshot: BeingSnapshot) -> None:
        if not isinstance(snapshot, BeingSnapshot):
            raise TypeError(
                f"snapshot must be BeingSnapshot, got {type(snapshot).__name__}"
            )
        self._snapshots[BeingId(snapshot.being_id_value)] = snapshot

    def find_by_id(self, being_id: BeingId) -> Being | None:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        snapshot = self._snapshots.get(being_id)
        if snapshot is None:
            return None
        return BeingSnapshotCodec.decode(snapshot)

    def find_snapshot_by_id(self, being_id: BeingId) -> BeingSnapshot | None:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        return self._snapshots.get(being_id)

    def exists(self, being_id: BeingId) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        return being_id in self._snapshots

    def delete(self, being_id: BeingId) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        return self._snapshots.pop(being_id, None) is not None

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
        out: list[Being] = []
        for snapshot in self._snapshots.values():
            if (
                snapshot.attachment_world_id == world_id.value
                and snapshot.attachment_player_id == player_id.value
            ):
                out.append(BeingSnapshotCodec.decode(snapshot))
        return out


__all__ = ["InMemoryBeingRepository"]
