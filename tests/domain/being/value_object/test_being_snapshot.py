"""BeingSnapshot の不変条件挙動 (all-or-nothing 構造の核)。"""

from __future__ import annotations

import pytest

from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
)
from ai_rpg_world.domain.being.value_object.being_snapshot import (
    CURRENT_SNAPSHOT_VERSION,
    BeingSnapshot,
)


def _minimal_snapshot(**overrides: object) -> BeingSnapshot:
    base: dict[str, object] = dict(
        being_id_value="ada",
        persona=Persona(name="アダ", first_person="わたし"),
        attachment_world_id=None,
        attachment_player_id=None,
        snapshot_version=CURRENT_SNAPSHOT_VERSION,
    )
    base.update(overrides)
    return BeingSnapshot(**base)  # type: ignore[arg-type]


class TestBeingSnapshotConstruction:
    """BeingSnapshot のコンストラクタ・不変条件挙動。"""

    def test_min_snapshot_can_create(self) -> None:
        """全 required フィールドが揃えば生成成功。"""
        snapshot = _minimal_snapshot()
        assert snapshot.being_id_value == "ada"
        assert snapshot.has_attachment is False
        assert snapshot.legacy_declared_memory_kinds == ()

    def test_attachment(self) -> None:
        """world / player 両方とも値があれば has_attachment は True。"""
        snapshot = _minimal_snapshot(attachment_world_id=1, attachment_player_id=2)
        assert snapshot.has_attachment is True


class TestBeingSnapshotPartialStateRejection:
    """all-or-nothing: 部分状態を構造的に禁止する挙動。"""

    def test_world_raises_exception(self) -> None:
        """world_id だけ非 None は部分状態として不許可。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="attachment"):
            _minimal_snapshot(attachment_world_id=1, attachment_player_id=None)

    def test_player_raises_exception(self) -> None:
        """player_id だけ非 None も部分状態として不許可。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="attachment"):
            _minimal_snapshot(attachment_world_id=None, attachment_player_id=2)

    def test_being_id_value_empty_string_raises_exception(self) -> None:
        """空文字の being_id は復元不能なので構造的に禁止。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="being_id_value"):
            _minimal_snapshot(being_id_value="")

    def test_snapshot_without_persona_needs_legacy_name(self) -> None:
        """人柄の無い snapshot は、読み捨てる古い名前を持たなければ BeingSnapshotIncompleteException を投げる。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="legacy_identity_name"):
            _minimal_snapshot(persona=None)

    def test_snapshot_without_persona_is_legacy(self) -> None:
        """人柄が無く古い名前を持つ snapshot は、古い snapshot から読んだものとして扱う。"""
        snapshot = _minimal_snapshot(
            persona=None, legacy_identity_name="agent_1", legacy_identity_first_person="わたし"
        )

        assert snapshot.has_legacy_identity is True
        assert _minimal_snapshot().has_legacy_identity is False

    def test_non_persona_raises_exception(self) -> None:
        """persona が Persona でなければ BeingSnapshotIncompleteException を投げる。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="persona"):
            _minimal_snapshot(persona="アダ")

    def test_non_tuple_legacy_memory_kinds_raises_exception(self) -> None:
        """古い宣言を list で渡すと tuple ではないので BeingSnapshotIncompleteException を投げる。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="tuple"):
            _minimal_snapshot(legacy_declared_memory_kinds=["episodic"])  # type: ignore[arg-type]

    def test_non_string_legacy_memory_kind_element_raises_exception(self) -> None:
        """古い宣言の要素が文字列でなければ BeingSnapshotIncompleteException を投げる。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="elements"):
            _minimal_snapshot(legacy_declared_memory_kinds=(1, 2))  # type: ignore[arg-type]

    def test_attachment_world_id_int_raises_exception(self) -> None:
        """attachment_world_id が int でなければ不許可。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="attachment_world_id"):
            _minimal_snapshot(attachment_world_id="1", attachment_player_id=2)  # type: ignore[arg-type]

    def test_snapshot_version_zero_raises_exception(self) -> None:
        """version は正の int。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="snapshot_version"):
            _minimal_snapshot(snapshot_version=0)

    def test_snapshot_version_bool_raises_exception(self) -> None:
        """bool は int 派生だが意味的に不正なので明示的に弾く。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="snapshot_version"):
            _minimal_snapshot(snapshot_version=True)  # type: ignore[arg-type]


class TestBeingSnapshotMemoryPayload:
    """Phase 4 Step 4-1: memory_payload_json フィールドの不変条件挙動。"""

    def test_memory_payload_none(self) -> None:
        """デフォルトでは memory_payload_json は None (= v1 互換挙動)。"""
        snapshot = _minimal_snapshot()
        assert snapshot.memory_payload_json is None
        assert snapshot.has_memory_payload is False

    def test_memory_payload_json_string(self) -> None:
        """非空 str を持つ snapshot は has_memory_payload True。"""
        snapshot = _minimal_snapshot(memory_payload_json='{"memo": []}')
        assert snapshot.memory_payload_json == '{"memo": []}'
        assert snapshot.has_memory_payload is True

    def test_memory_payload_empty_string_raises_exception(self) -> None:
        """has_memory_payload=True なのに中身が空、を構造的に禁止する。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="non-empty"):
            _minimal_snapshot(memory_payload_json="")

    def test_memory_payload_str_raises_exception(self) -> None:
        """memory_payload_json は str | None 以外不許可。"""
        with pytest.raises(BeingSnapshotIncompleteException, match="memory_payload_json"):
            _minimal_snapshot(memory_payload_json=123)  # type: ignore[arg-type]

    def test_default_snapshot_version_value(self) -> None:
        """``CURRENT_SNAPSHOT_VERSION`` が dataclass default として使われている。"""
        snapshot = BeingSnapshot(
            being_id_value="ada",
            persona=Persona(name="アダ"),
            attachment_world_id=None,
            attachment_player_id=None,
        )
        assert snapshot.snapshot_version == CURRENT_SNAPSHOT_VERSION


class TestBeingSnapshotEquality:
    """BeingSnapshot の等価性 (frozen dataclass)。"""

    def test_same_equals(self) -> None:
        """全フィールド同値なら ``==`` が True。"""
        assert _minimal_snapshot() == _minimal_snapshot()

    def test_persona_not_equal(self) -> None:
        """人柄が違えば等しくない。"""
        assert _minimal_snapshot(persona=Persona(name="アダ")) != _minimal_snapshot(persona=Persona(name="ベン"))
