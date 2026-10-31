"""BeingSnapshotCodec の Being ↔ BeingSnapshot 変換挙動。"""

from __future__ import annotations

from dataclasses import replace

import pytest

from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.being_attachment import BeingAttachment
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
    BeingSnapshotVersionException,
)
from ai_rpg_world.domain.being.service.being_snapshot_codec import (
    BeingSnapshotCodec,
)
from ai_rpg_world.domain.being.value_object.being_snapshot import (
    CURRENT_SNAPSHOT_VERSION,
    BeingSnapshot,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import WorldId


def _persona() -> Persona:
    return Persona(
        name="アダ",
        first_person="わたし",
        speech="丁寧語",
        traits=("慎重", "観察好き"),
        values=("約束",),
        fears=("暗闇",),
        background="港町で育った。",
    )


def _attached_being() -> Being:
    return Being(
        being_id=BeingId("ada"),
        persona=_persona(),
        attachment=BeingAttachment(environment_id="w1p2", environment_name="廃坑の山村"),
    )


def _snapshot(**overrides: object) -> BeingSnapshot:
    fields: dict[str, object] = dict(
        being_id_value="ada",
        persona=_persona(),
        attachment_environment_id=None,
        attachment_environment_name=None,
    )
    fields.update(overrides)
    return BeingSnapshot(**fields)  # type: ignore[arg-type]


class TestBeingSnapshotCodecEncode:
    """encode (Being → BeingSnapshot) の挙動。"""

    def test_attach_being_encode(self) -> None:
        """attachment なしの Being は snapshot の attachment 両 None で表現。"""
        being = Being(being_id=BeingId("ada"), persona=_persona())
        snapshot = BeingSnapshotCodec.encode(being)
        assert snapshot.being_id_value == "ada"
        assert snapshot.persona == _persona()
        assert snapshot.attachment_environment_id is None
        assert snapshot.attachment_environment_name is None
        assert snapshot.legacy_declared_memory_kinds == ()
        assert snapshot.snapshot_version == CURRENT_SNAPSHOT_VERSION

    def test_attach_being_encode_attachment(
        self,
    ) -> None:
        """attached Being の snapshot は world / player 両方を持つ。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being())
        assert snapshot.attachment_environment_id == "w1p2"
        assert snapshot.attachment_environment_name == "廃坑の山村"

    def test_being_raises_type_error(self) -> None:
        """型違反は TypeError で弾く。"""
        with pytest.raises(TypeError):
            BeingSnapshotCodec.encode("not-a-being")  # type: ignore[arg-type]


class TestBeingSnapshotCodecDecode:
    """decode (BeingSnapshot → Being) の挙動。"""

    def test_encode_decode_being_state(self) -> None:
        """encode して decode すると、ID・人柄のすべての項目・所属が元の Being と一致する。"""
        original = _attached_being()
        decoded = BeingSnapshotCodec.decode(BeingSnapshotCodec.encode(original))
        assert decoded.being_id == original.being_id
        assert decoded.persona == original.persona
        assert decoded.attachment == original.attachment

    def test_attach_snapshot_decode_attachment_none(self) -> None:
        """attachment 両 None の snapshot は未 attach Being として復元される。"""
        being = BeingSnapshotCodec.decode(_snapshot())
        assert being.attachment is None
        assert being.is_attached is False

    def test_snapshot_without_persona_is_not_decoded(self) -> None:
        """人柄で埋める前の古い snapshot は decode せず、BeingSnapshotIncompleteException を投げる。"""
        snapshot = _snapshot(persona=None, legacy_identity_name="agent_1")

        with pytest.raises(BeingSnapshotIncompleteException, match="persona"):
            BeingSnapshotCodec.decode(snapshot)

    def test_raises_unsupported_version_being_snapshot_version_exception(
        self,
    ) -> None:
        """未サポート version は明示的にバージョン例外として弾く。"""
        snapshot = _snapshot(snapshot_version=999)
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
        snapshot = BeingSnapshotCodec.encode(_attached_being(), memory_payload_json='{"memo": [], "semantic": []}')
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
                _attached_being(),
                memory_payload_json=123,  # type: ignore[arg-type]
            )

    def test_v1_snapshot_decode(self) -> None:
        """SUPPORTED_VERSIONS が v1 を含むため後方互換で復元可能。"""
        snapshot = _snapshot(
            attachment_environment_id="w1p2", attachment_environment_name="廃坑の山村", snapshot_version=1
        )
        being = BeingSnapshotCodec.decode(snapshot)
        assert being.being_id == BeingId("ada")
        assert being.attachment is not None

    def test_v_one_snapshot_memory_payload_raises_exception(self) -> None:
        """v1 と memory_payload_json の組み合わせは整合性エラー。"""
        snapshot = _snapshot(snapshot_version=1, memory_payload_json='{"memo": []}')
        with pytest.raises(BeingSnapshotIncompleteException, match="v1"):
            BeingSnapshotCodec.decode(snapshot)

    def test_decode_being_restore_payload(self) -> None:
        """memory payload は Phase 4-2 の service 責務なので codec では復元しない。"""
        snapshot = BeingSnapshotCodec.encode(_attached_being(), memory_payload_json='{"any": "thing"}')
        being = BeingSnapshotCodec.decode(snapshot)
        assert being.attachment is not None
        assert being.persona == _persona()

    def test_v2_snapshot_round_trip(self) -> None:
        """encode → decode → encode で payload も保持される。"""
        being = _attached_being()
        payload = '{"memo": [{"id": "m1"}]}'
        s1 = BeingSnapshotCodec.encode(being, memory_payload_json=payload)
        decoded = BeingSnapshotCodec.decode(s1)
        s2 = BeingSnapshotCodec.encode(decoded, memory_payload_json=payload)
        assert s2 == s1


class TestRemovedMemoryDeclaration:
    """古い snapshot に残る記憶の種類の宣言を、どの値でも数えて読み捨てることを保証する (design_decisions D1469-1)。"""

    @pytest.mark.parametrize("version", [1, 2])
    def test_old_declarations_are_counted_by_kind(self, version: int) -> None:
        """古い宣言は、廃止済みの semantic も未知の値も拒まず、種類ごとの件数として数える。"""
        snapshot = _snapshot(
            snapshot_version=version,
            legacy_declared_memory_kinds=("semantic", "memo", "semantic", "unknown_kind"),
        )

        assert BeingSnapshotCodec.removed_declared_memory_kind_counts(snapshot) == {
            "semantic": 2,
            "memo": 1,
            "unknown_kind": 1,
        }

    def test_snapshot_without_old_declarations_counts_nothing(self) -> None:
        """宣言を持たない snapshot は、読み捨てた件数を空で返す。"""
        assert BeingSnapshotCodec.removed_declared_memory_kind_counts(_snapshot()) == {}

    def test_old_declarations_do_not_come_back_on_reencode(self) -> None:
        """古い宣言のある snapshot を decode して encode し直すと、宣言は残らず ID・人柄・所属は保たれる。"""
        snapshot = _snapshot(
            attachment_environment_id="w1p2",
            attachment_environment_name="廃坑の山村",
            legacy_declared_memory_kinds=("episodic", "memo"),
        )

        encoded = BeingSnapshotCodec.encode(BeingSnapshotCodec.decode(snapshot))

        assert encoded == replace(snapshot, legacy_declared_memory_kinds=())
