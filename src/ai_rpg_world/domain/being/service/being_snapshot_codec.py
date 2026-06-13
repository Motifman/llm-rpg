"""BeingSnapshotCodec — Being 集約 ↔ BeingSnapshot の変換ドメインサービス。

PR #462 §2.1 R1: 「all-or-nothing で復元の完全性を保証 (部分復元を構造的に禁止)」
を実装する。本 codec は **decode 時に部分状態を検出して例外** を投げることで、
構造的に不完全な Being 復元を不可能にする。

責務:

- ``encode(being)``: Being 集約から BeingSnapshot を作る (常に成功)
- ``decode(snapshot)``: BeingSnapshot から Being 集約を復元
  - snapshot version が現 codec で読めない値なら ``BeingSnapshotVersionException``
  - memory_kind 文字列が認識できなければ ``BeingSnapshotIncompleteException``
  - その他 VO レベルの形式エラーは VO 自身のドメイン例外 (BeingId 等) で検出
"""

from __future__ import annotations

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
    BeingSnapshotVersionException,
)
from ai_rpg_world.domain.being.value_object.being_attachment import BeingAttachment
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.being.value_object.being_identity import BeingIdentity
from ai_rpg_world.domain.being.value_object.being_snapshot import (
    CURRENT_SNAPSHOT_VERSION,
    BeingSnapshot,
)
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingSnapshotCodec:
    """Being 集約 ↔ BeingSnapshot の変換ドメインサービス。

    本 codec はステートレス。全メソッドは ``@staticmethod`` で公開する。
    """

    SUPPORTED_VERSIONS: frozenset[int] = frozenset({CURRENT_SNAPSHOT_VERSION})

    @staticmethod
    def encode(being: Being) -> BeingSnapshot:
        """Being 集約をシリアライズ可能な snapshot に変換する。"""
        if not isinstance(being, Being):
            raise TypeError(f"being must be Being, got {type(being).__name__}")

        attachment = being.attachment
        world_id_value: int | None = None
        player_id_value: int | None = None
        if attachment is not None:
            world_id_value = attachment.world_id.value
            player_id_value = attachment.player_id.value

        return BeingSnapshot(
            being_id_value=being.being_id.value,
            identity_name=being.identity.name,
            identity_first_person=being.identity.first_person,
            attachment_world_id=world_id_value,
            attachment_player_id=player_id_value,
            declared_memory_kinds=tuple(
                sorted(k.value for k in being.declared_memory_kinds)
            ),
            snapshot_version=CURRENT_SNAPSHOT_VERSION,
        )

    @staticmethod
    def decode(snapshot: BeingSnapshot) -> Being:
        """BeingSnapshot から Being 集約を復元する (all-or-nothing)。"""
        if not isinstance(snapshot, BeingSnapshot):
            raise TypeError(
                f"snapshot must be BeingSnapshot, got {type(snapshot).__name__}"
            )

        if snapshot.snapshot_version not in BeingSnapshotCodec.SUPPORTED_VERSIONS:
            raise BeingSnapshotVersionException(
                f"snapshot_version={snapshot.snapshot_version} is not supported "
                f"by this codec (supported: "
                f"{sorted(BeingSnapshotCodec.SUPPORTED_VERSIONS)})"
            )

        being_id = BeingId(snapshot.being_id_value)
        identity = BeingIdentity(
            name=snapshot.identity_name,
            first_person=snapshot.identity_first_person,
        )

        attachment: BeingAttachment | None = None
        if snapshot.has_attachment:
            # BeingSnapshot.__post_init__ が「両 None or 両非 None」を保証して
            # いるので本来到達不能だが、python -O で assert が剥がれた場合の
            # 安全側として明示ガードする (= 黙って partial state を通さない)。
            if (
                snapshot.attachment_world_id is None
                or snapshot.attachment_player_id is None
            ):
                raise BeingSnapshotIncompleteException(
                    "has_attachment is True but attachment ids are None "
                    "(BeingSnapshot invariant violated)"
                )
            attachment = BeingAttachment(
                world_id=WorldId(snapshot.attachment_world_id),
                player_id=PlayerId(snapshot.attachment_player_id),
            )

        kinds: list[MemoryKind] = []
        valid_values = {k.value for k in MemoryKind}
        for raw in snapshot.declared_memory_kinds:
            if raw not in valid_values:
                raise BeingSnapshotIncompleteException(
                    f"unknown memory_kind value in snapshot: {raw!r} "
                    f"(known: {sorted(valid_values)})"
                )
            kinds.append(MemoryKind(raw))

        return Being(
            being_id=being_id,
            identity=identity,
            attachment=attachment,
            declared_memory_kinds=kinds,
        )


__all__ = ["BeingSnapshotCodec"]
