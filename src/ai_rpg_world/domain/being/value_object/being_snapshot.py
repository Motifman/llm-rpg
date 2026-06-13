"""BeingSnapshot — Being 集約のシリアライズ可能な不変表現。

PR #462 §2.1 R1: 「永続化は store 単位 env ではなく Being 単位の設定 1 箇所」「復元
の完全性は all-or-nothing で保証 (部分復元を構造的に禁止)」を実現するための中間
形式。Phase 2 PR4 (本 PR) では Being 集約 root の状態 (identity + attachment +
declared_memory_kinds) のみを内包する。

memory store の中身そのものは含まない (= 集約粒度方針 (b) に従い、Phase 3 で
being_id keyed への移行が完了した後、本 snapshot に payload field を増やす形で
拡張する想定)。

## 不変条件 (all-or-nothing 構造の核)

1. ``being_id_value`` / ``identity_name`` / ``identity_first_person`` は非空
2. ``attachment_world_id`` と ``attachment_player_id`` は **両方 None または両方
   非 None** でなければならない (= 片方だけ埋まる部分状態を構造的に禁止)
3. ``declared_memory_kinds`` は str のタプル (中身が認識可能な MemoryKind 値か
   どうかは codec の decode 時にチェックする = VO 自体は形式のみガード)
4. ``snapshot_version`` は正の int

これらが満たされない場合は ``BeingSnapshotIncompleteException`` を投げる。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
)


CURRENT_SNAPSHOT_VERSION: int = 1


@dataclass(frozen=True)
class BeingSnapshot:
    """Being 集約のシリアライズ可能な不変表現。"""

    being_id_value: str
    identity_name: str
    identity_first_person: str
    attachment_world_id: int | None
    attachment_player_id: int | None
    declared_memory_kinds: tuple[str, ...]
    snapshot_version: int = CURRENT_SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        self._reject_blank("being_id_value", self.being_id_value)
        self._reject_blank("identity_name", self.identity_name)
        self._reject_blank("identity_first_person", self.identity_first_person)
        self._validate_attachment_pair()
        self._validate_memory_kinds()
        self._validate_version()

    @staticmethod
    def _reject_blank(field: str, value: object) -> None:
        if not isinstance(value, str):
            raise BeingSnapshotIncompleteException(
                f"BeingSnapshot.{field} must be str, got {type(value).__name__}"
            )
        if not value.strip():
            raise BeingSnapshotIncompleteException(
                f"BeingSnapshot.{field} must be non-empty"
            )

    def _validate_attachment_pair(self) -> None:
        world = self.attachment_world_id
        player = self.attachment_player_id
        if (world is None) ^ (player is None):
            raise BeingSnapshotIncompleteException(
                "BeingSnapshot attachment fields must be both None or both set; "
                f"got world_id={world!r}, player_id={player!r}"
            )
        if world is not None and not isinstance(world, int):
            raise BeingSnapshotIncompleteException(
                f"attachment_world_id must be int or None, got {type(world).__name__}"
            )
        if player is not None and not isinstance(player, int):
            raise BeingSnapshotIncompleteException(
                f"attachment_player_id must be int or None, got {type(player).__name__}"
            )

    def _validate_memory_kinds(self) -> None:
        if not isinstance(self.declared_memory_kinds, tuple):
            raise BeingSnapshotIncompleteException(
                "declared_memory_kinds must be tuple, "
                f"got {type(self.declared_memory_kinds).__name__}"
            )
        for kind in self.declared_memory_kinds:
            if not isinstance(kind, str):
                raise BeingSnapshotIncompleteException(
                    "declared_memory_kinds elements must be str, "
                    f"got {type(kind).__name__}"
                )

    def _validate_version(self) -> None:
        # bool は int 派生なので True/False が黙って通らないよう明示的に排除する。
        if (
            isinstance(self.snapshot_version, bool)
            or not isinstance(self.snapshot_version, int)
            or self.snapshot_version <= 0
        ):
            raise BeingSnapshotIncompleteException(
                f"snapshot_version must be positive int, got {self.snapshot_version!r}"
            )

    @property
    def has_attachment(self) -> bool:
        """attachment 情報を持つ snapshot なら True。"""
        return self.attachment_world_id is not None


__all__ = ["BeingSnapshot", "CURRENT_SNAPSHOT_VERSION"]
