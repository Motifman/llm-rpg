"""BeingSnapshotCodec — Being 集約 ↔ BeingSnapshot の変換ドメインサービス。

PR #462 §2.1 R1: 「all-or-nothing で復元の完全性を保証 (部分復元を構造的に禁止)」
を実装する。本 codec は **decode 時に部分状態を検出して例外** を投げることで、
構造的に不完全な Being 復元を不可能にする。

責務:

- ``encode(being, *, memory_payload_json=None)``: Being 集約から BeingSnapshot を作る。
  ``memory_payload_json`` を渡すと snapshot_version=2 として memory payload も
  保持する。未指定なら v1 互換の snapshot (memory_payload_json=None) になる
- ``decode(snapshot)``: BeingSnapshot から Being 集約を復元
  - snapshot version が現 codec で読めない値なら ``BeingSnapshotVersionException``
  - memory_kind 文字列が認識できなければ ``BeingSnapshotIncompleteException``
  - その他 VO レベルの形式エラーは VO 自身のドメイン例外 (BeingId 等) で検出

Phase 4 Step 4-1: memory payload は本 codec ではオペーク扱い。実際の memory
store への書き戻しは ``BeingMemorySnapshotService`` (application 層、4-2 で
実装) が担当する。
"""

from __future__ import annotations

from typing import Optional

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
    LEGACY_SNAPSHOT_VERSION_V1,
    BeingSnapshot,
)
from ai_rpg_world.domain.being.value_object.memory_kind import MemoryKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


class BeingSnapshotCodec:
    """Being 集約 ↔ BeingSnapshot の変換ドメインサービス。

    本 codec はステートレス。全メソッドは ``@staticmethod`` で公開する。

    Phase 4 Step 4-1: v1 と v2 の両 snapshot を decode 可能 (= 後方互換)。
    encode は ``memory_payload_json`` の有無で v1 / v2 を切り替える。
    """

    SUPPORTED_VERSIONS: frozenset[int] = frozenset(
        {LEGACY_SNAPSHOT_VERSION_V1, CURRENT_SNAPSHOT_VERSION}
    )

    @staticmethod
    def encode(
        being: Being,
        *,
        memory_payload_json: Optional[str] = None,
    ) -> BeingSnapshot:
        """Being 集約をシリアライズ可能な snapshot に変換する。

        encode は常に最新版 (= v2) snapshot を返す。``memory_payload_json``
        を渡せば payload 付き、未指定なら ``memory_payload_json=None`` の
        v2 snapshot になる (= 「memory を載せていない最新版 snapshot」)。
        v1 はあくまで ``decode`` 経路の後方互換用バージョン。

        Phase 4 Step 4-1: memory payload は本 codec ではオペーク扱い。JSON
        valid かどうかは渡す側 (= BeingMemorySnapshotService) の責務。
        """
        if not isinstance(being, Being):
            raise TypeError(f"being must be Being, got {type(being).__name__}")
        if memory_payload_json is not None and not isinstance(
            memory_payload_json, str
        ):
            raise TypeError(
                "memory_payload_json must be str or None, "
                f"got {type(memory_payload_json).__name__}"
            )

        attachment = being.attachment
        world_id_value: int | None = None
        player_id_value: int | None = None
        if attachment is not None:
            world_id_value = attachment.world_id.value
            player_id_value = attachment.player_id.value

        # encode は常に最新版 (= v2) を出す。memory_payload_json=None でも v2 と
        # して扱う (= 「memory がまだ取得されていない v2 snapshot」は意味的に
        # 有効)。v1 はあくまで decode 経路の後方互換用。
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
            memory_payload_json=memory_payload_json,
        )

    @staticmethod
    def decode(snapshot: BeingSnapshot) -> Being:
        """BeingSnapshot から Being 集約を復元する (all-or-nothing)。

        Phase 4 Step 4-1: v1 / v2 snapshot 両対応。memory payload は本 codec
        では復元しない (= Being 集約 root の状態のみ復元)。memory store への
        書き戻しは ``BeingMemorySnapshotService.restore`` の責務。

        version 検査の不一致は ``BeingSnapshotVersionException``。
        """
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

        # v1 snapshot に memory payload が紛れていたら整合性エラー (codec の
        # 信頼性を担保)。
        if (
            snapshot.snapshot_version == LEGACY_SNAPSHOT_VERSION_V1
            and snapshot.memory_payload_json is not None
        ):
            raise BeingSnapshotIncompleteException(
                "v1 snapshot must not carry memory_payload_json; "
                "use snapshot_version=2 for memory payload"
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
