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

    def test_attach_being_encode(self) -> None:
        """attachment なしの Being は snapshot の attachment 両 None で表現。"""
        being = Being(being_id=BeingId("ada"), identity=_identity())
        snapshot = BeingSnapshotCodec.encode(being)
        assert snapshot.being_id_value == "ada"
        assert snapshot.identity_name == "アダ"
        assert snapshot.attachment_world_id is None
        assert snapshot.attachment_player_id is None
        assert snapshot.declared_memory_kinds == ()
        assert snapshot.snapshot_version == CURRENT_SNAPSHOT_VERSION

    def test_attach_being_encode_attachment(
        self,
    ) -> None:
        """attached Being の snapshot は world / player 両方を持つ。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being())
        assert snapshot.attachment_world_id == 1
        assert snapshot.attachment_player_id == 2

    def test_declared_memory_kinds_value_string_tuple(self) -> None:
        """encode 後の memory_kinds は str tuple かつ決定的 (sorted)。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being())
        assert snapshot.declared_memory_kinds == ("episodic", "memo")

    def test_being_raises_type_error(self) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            BeingSnapshotCodec.encode("not-a-being")  # type: ignore[arg-type]


class TestBeingSnapshotCodecDecode:
    """decode (BeingSnapshot → Being) の挙動。"""

    def test_encode_decode_being_state(self) -> None:
        """ラウンドトリップで Being の全状態 (id / identity / attachment / kinds) が一致。"""
        original = _attached_being()
        decoded = BeingSnapshotCodec.decode(BeingSnapshotCodec.encode(original))
        assert decoded.being_id == original.being_id
        assert decoded.identity == original.identity
        assert decoded.attachment == original.attachment
        assert decoded.declared_memory_kinds == original.declared_memory_kinds

    def test_attach_snapshot_decode_attachment_none(self) -> None:
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

    def test_raises_unknown_memory_kind_being_snapshot_incomplete_exception(
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

    def test_raises_unsupported_version_being_snapshot_version_exception(
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

    def test_being_snapshot_raises_type_error(self) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            BeingSnapshotCodec.decode({"being_id_value": "ada"})  # type: ignore[arg-type]


class TestBeingSnapshotCodecMemoryPayload:
    """Phase 4 Step 4-1: memory payload を載せた v2 snapshot の挙動。"""

    def test_memory_payload_encode_snapshot_preserved(self) -> None:
        """``memory_payload_json`` を渡すと snapshot にそのまま乗る。"""
        snapshot = BeingSnapshotCodec.encode(
            _attached_being(), memory_payload_json='{"memo": [], "semantic": []}'
        )
        assert snapshot.memory_payload_json == '{"memo": [], "semantic": []}'
        assert snapshot.snapshot_version == CURRENT_SNAPSHOT_VERSION
        assert snapshot.has_memory_payload is True

    def test_encode_snapshot(self) -> None:
        """memory_payload_json=None でも v2 snapshot として出す。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being())
        assert snapshot.snapshot_version == CURRENT_SNAPSHOT_VERSION
        assert snapshot.memory_payload_json is None
        assert snapshot.has_memory_payload is False

    def test_memory_payload_str_raises_type_error(self) -> None:
        """渡し間違いは TypeError で弾く (= 形式エラーは早期に検出)。"""
        with pytest.raises(TypeError, match="memory_payload_json"):
            BeingSnapshotCodec.encode(
                _attached_being(), memory_payload_json=123  # type: ignore[arg-type]
            )

    def test_v1_snapshot_decode(self) -> None:
        """SUPPORTED_VERSIONS が v1 を含むため後方互換で復元可能。"""
        snapshot = BeingSnapshot(
            being_id_value="ada",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=1,
            attachment_player_id=2,
            declared_memory_kinds=("episodic",),
            snapshot_version=1,
        )
        being = BeingSnapshotCodec.decode(snapshot)
        assert being.being_id == BeingId("ada")
        assert being.attachment is not None

    def test_v_one_snapshot_memory_payload_raises_exception(self) -> None:
        """v1 と memory_payload_json の組み合わせは整合性エラー。"""
        snapshot = BeingSnapshot(
            being_id_value="ada",
            identity_name="アダ",
            identity_first_person="わたし",
            attachment_world_id=None,
            attachment_player_id=None,
            declared_memory_kinds=(),
            snapshot_version=1,
            memory_payload_json='{"memo": []}',
        )
        with pytest.raises(BeingSnapshotIncompleteException, match="v1"):
            BeingSnapshotCodec.decode(snapshot)

    def test_decode_being_restore_payload(self) -> None:
        """memory payload は Phase 4-2 の service 責務なので codec では復元しない。"""
        snapshot = BeingSnapshotCodec.encode(
            _attached_being(), memory_payload_json='{"any": "thing"}'
        )
        being = BeingSnapshotCodec.decode(snapshot)
        # codec は Being 集約 root の状態 (identity / attachment / kinds) だけ復元
        assert being.attachment is not None
        assert MemoryKind.EPISODIC in being.declared_memory_kinds

    def test_v2_snapshot_round_trip(self) -> None:
        """encode → decode → encode で payload も保持される。"""
        being = _attached_being()
        payload = '{"memo": [{"id": "m1"}]}'
        s1 = BeingSnapshotCodec.encode(being, memory_payload_json=payload)
        decoded = BeingSnapshotCodec.decode(s1)
        s2 = BeingSnapshotCodec.encode(decoded, memory_payload_json=payload)
        assert s2 == s1
