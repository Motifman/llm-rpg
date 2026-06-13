"""BeingSnapshotCodec の Being ↔ BeingSnapshot 変換挙動。"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
    BeingSnapshotVersionException,
)
from ai_rpg_world.domain.being.service.being_snapshot_codec import (
    BeingSnapshotCodec,
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


def _identity() -> BeingIdentity:
    return BeingIdentity(name="アダ", first_person="わたし")


def _attached_being() -> Being:
    return Being(
        being_id=BeingId("ada"),
        identity=_identity(),
        attachment=BeingAttachment(world_id=WorldId(1), player_id=PlayerId(2)),
        declared_memory_kinds=[MemoryKind.EPISODIC, MemoryKind.MEMO],
    )


class TestBeingSnapshotCodecEncode:
    """encode (Being → BeingSnapshot) の挙動。"""

    def test_未_attach_の_Being_を_encode_できる(self) -> None:
        """attachment なしの Being は snapshot の attachment 両 None で表現。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        snapshot = BeingSnapshotCodec.encode(being)
        assert snapshot.being_id_value == "ada"
        assert snapshot.identity_name == "アダ"
        assert snapshot.attachment_world_id is None
        assert snapshot.attachment_player_id is None
        assert snapshot.declared_memory_kinds == ()
        assert snapshot.snapshot_version == CURRENT_SNAPSHOT_VERSION

    def test_attach_済み_Being_を_encode_すると_attachment_両フィールドが入る(
        self,
    ) -> None:
        """attached Being の snapshot は world / player 両方を持つ。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being())
        assert snapshot.attachment_world_id == 1
        assert snapshot.attachment_player_id == 2

    def test_declared_memory_kinds_は_value_文字列の_tuple_になる(self) -> None:
        """encode 後の memory_kinds は str tuple かつ決定的 (sorted)。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being())
        assert snapshot.declared_memory_kinds == ("episodic", "memo")

    def test_非_Being_を渡すと_TypeError(self) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            BeingSnapshotCodec.encode("not-a-being")  # type: ignore[arg-type]


class TestBeingSnapshotCodecDecode:
    """decode (BeingSnapshot → Being) の挙動。"""

    def test_encode_decode_で_Being_の状態が保たれる(self) -> None:
        """ラウンドトリップで Being の全状態 (id / identity / attachment / kinds) が一致。"""
        original = _attached_being()
        decoded = BeingSnapshotCodec.decode(BeingSnapshotCodec.encode(original))
        assert decoded.being_id == original.being_id
        assert decoded.identity == original.identity
        assert decoded.attachment == original.attachment
        assert decoded.declared_memory_kinds == original.declared_memory_kinds

    def test_未_attach_の_snapshot_を_decode_すると_attachment_は_None(self) -> None:
        """attachment 両 None の snapshot は未 attach Being として復元される。"""
        snapshot = BeingSnapshot(
            being_id_value="ada",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=None,
            attachment_player_id=None,
            declared_memory_kinds=(),
        )
        being = BeingSnapshotCodec.decode(snapshot)
        assert being.attachment is None
        assert being.is_attached is False

    def test_未知の_memory_kind_は_BeingSnapshotIncompleteException_を投げる(
        self,
    ) -> None:
        """codec が認識できない memory_kind 文字列は all-or-nothing 違反。"""
        snapshot = BeingSnapshot(
            being_id_value="ada",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=None,
            attachment_player_id=None,
            declared_memory_kinds=("unknown_kind",),
        )
        with pytest.raises(BeingSnapshotIncompleteException, match="unknown_kind"):
            BeingSnapshotCodec.decode(snapshot)

    def test_未サポートの_version_は_BeingSnapshotVersionException_を投げる(
        self,
    ) -> None:
        """未サポート version は明示的にバージョン例外として弾く。"""
        snapshot = BeingSnapshot(
            being_id_value="ada",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=None,
            attachment_player_id=None,
            declared_memory_kinds=(),
            snapshot_version=999,
        )
        with pytest.raises(BeingSnapshotVersionException, match="999"):
            BeingSnapshotCodec.decode(snapshot)

    def test_非_BeingSnapshot_を渡すと_TypeError(self) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            BeingSnapshotCodec.decode({"being_id_value": "ada"})  # type: ignore[arg-type]
