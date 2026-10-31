"""BeingSnapshotFileGateway の I/O 挙動 (Phase 5)。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
    dict_to_snapshot,
    snapshot_to_dict,
)
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
)
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot


def _snapshot(
    *,
    memory_payload_json: str | None = '{"memo": []}',
) -> BeingSnapshot:
    return BeingSnapshot(
        being_id_value="being_w1_p1",
        persona=Persona(
            name="アダ",
            first_person="わたし",
            speech="丁寧語",
            traits=("慎重",),
            values=("約束",),
            fears=("暗闇",),
            background="港町で育った。",
        ),
        attachment_world_id=1,
        attachment_player_id=1,
        snapshot_version=2,
        memory_payload_json=memory_payload_json,
    )


class TestSnapshotToDict:
    """snapshot_to_dict / dict_to_snapshot の挙動。"""

    def test_returns_round_trip_snapshot(self) -> None:
        """roundtrip で等価な snapshot が返る。"""
        original = _snapshot()
        restored = dict_to_snapshot(snapshot_to_dict(original))
        assert restored == original

    def test_payload_none_round_trip(self) -> None:
        """payload None でも round trip できる。"""
        original = _snapshot(memory_payload_json=None)
        assert dict_to_snapshot(snapshot_to_dict(original)) == original

    def test_being_snapshot_raises_type_error(self) -> None:
        """非 BeingSnapshot は TypeError。"""
        with pytest.raises(TypeError):
            snapshot_to_dict({"not": "snapshot"})  # type: ignore[arg-type]

    def test_non_dict_raises_incomplete(self) -> None:
        """dict でない値を渡すと BeingSnapshotIncompleteException を投げる。"""
        with pytest.raises(BeingSnapshotIncompleteException):
            dict_to_snapshot("bad")  # type: ignore[arg-type]

    def test_all_dict_being_snapshot_rejected(self) -> None:
        """不完全な dict は BeingSnapshot 不変条件で弾かれる。"""
        bad = {
            "being_id_value": "",  # 空文字 → 不変条件違反
            "persona": {"name": "n"},
            "attachment_world_id": None,
            "attachment_player_id": None,
            "snapshot_version": 2,
            "memory_payload_json": None,
        }
        with pytest.raises(BeingSnapshotIncompleteException):
            dict_to_snapshot(bad)


class TestPersonaInSnapshotDict:
    """人柄を ``persona`` に書き、persona の無い古い snapshot も読めることを保証する (design_decisions D1469-1)。"""

    def test_dict_has_persona_and_no_old_keys(self) -> None:
        """書き出す dict は人柄を ``persona`` に入れ、消した ``identity_*`` と ``declared_memory_kinds`` を持たない。"""
        data = snapshot_to_dict(_snapshot())

        assert data["persona"] == {
            "name": "アダ",
            "first_person": "わたし",
            "speech": "丁寧語",
            "traits": ["慎重"],
            "values": ["約束"],
            "fears": ["暗闇"],
            "background": "港町で育った。",
        }
        assert not {"identity_name", "identity_first_person", "declared_memory_kinds"} & data.keys()

    def test_old_snapshot_drops_name_and_first_person(self) -> None:
        """persona の無い古い snapshot は人柄を持たず、identity_name と identity_first_person は読み捨てる値として持つ。"""
        old = {
            "being_id_value": "being_w1_p1",
            "identity_name": "agent_1",
            "identity_first_person": "わたし",
            "attachment_world_id": 1,
            "attachment_player_id": 1,
            "declared_memory_kinds": ["episodic", "memo", "semantic"],
            "snapshot_version": 2,
            "memory_payload_json": None,
        }

        snapshot = dict_to_snapshot(old)

        assert snapshot.persona is None
        assert (snapshot.legacy_identity_name, snapshot.legacy_identity_first_person) == ("agent_1", "わたし")
        assert snapshot.legacy_declared_memory_kinds == ("episodic", "memo", "semantic")

    def test_snapshot_without_persona_cannot_be_written(self) -> None:
        """人柄で埋める前の古い snapshot を書き出そうとすると BeingSnapshotIncompleteException を投げる。"""
        data = snapshot_to_dict(_snapshot())
        del data["persona"]
        data.update(identity_name="agent_1", identity_first_person="わたし")

        with pytest.raises(BeingSnapshotIncompleteException, match="persona"):
            snapshot_to_dict(dict_to_snapshot(data))

    def test_persona_with_missing_optional_keys_reads_as_undecided(self) -> None:
        """persona に名前しか無ければ、ほかの人柄は決まっていないものとして読む。"""
        data = snapshot_to_dict(_snapshot())
        data["persona"] = {"name": "アダ"}

        assert dict_to_snapshot(data).persona == Persona(name="アダ")

    @pytest.mark.parametrize("key", ["traits", "values", "fears"])
    def test_non_list_persona_list_raises_incomplete(self, key: str) -> None:
        """persona の性格・大事にしていること・怖いものが JSON の配列でなければ BeingSnapshotIncompleteException を投げる。"""
        data = snapshot_to_dict(_snapshot())
        data["persona"][key] = "慎重"

        with pytest.raises(BeingSnapshotIncompleteException, match=key):
            dict_to_snapshot(data)


class TestFileGateway:
    """ローカルファイル I/O の round-trip。"""

    def test_write_read_matches(self, tmp_path: Path) -> None:
        """write して read すると一致する。"""
        gateway = BeingSnapshotFileGateway()
        snapshot = _snapshot()
        path = tmp_path / "snap.json"
        gateway.write(snapshot, path)
        assert gateway.read(path) == snapshot

    def test_written_json_human_readable_dict(self, tmp_path: Path) -> None:
        """ensure_ascii=False + indent=2 で読みやすい形式。"""
        gateway = BeingSnapshotFileGateway()
        path = tmp_path / "snap.json"
        gateway.write(_snapshot(), path)
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # 日本語の人柄がそのまま入る (ensure_ascii=False の効果)。
        assert "アダ" in raw
        assert data["snapshot_version"] == 2

    def test_value_raises_type_error(self, tmp_path: Path) -> None:
        """型違反は TypeError。"""
        gateway = BeingSnapshotFileGateway()
        with pytest.raises(TypeError):
            gateway.write("bad", tmp_path / "x.json")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            gateway.read("string-not-path")  # type: ignore[arg-type]
