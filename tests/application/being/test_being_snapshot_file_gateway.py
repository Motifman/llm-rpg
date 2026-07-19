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
        identity_name="アダ",
        identity_first_person="わたし",
        attachment_world_id=1,
        attachment_player_id=1,
        declared_memory_kinds=("memo",),
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

    def test_dict_raises_type_error(self) -> None:
        """dict でないと TypeError。"""
        with pytest.raises(TypeError):
            dict_to_snapshot("bad")  # type: ignore[arg-type]

    def test_all_dict_being_snapshot_rejected(self) -> None:
        """不完全な dict は BeingSnapshot 不変条件で弾かれる。"""
        bad = {
            "being_id_value": "",  # 空文字 → 不変条件違反
            "identity_name": "n",
            "identity_first_person": "i",
            "attachment_world_id": None,
            "attachment_player_id": None,
            "declared_memory_kinds": [],
            "snapshot_version": 2,
            "memory_payload_json": None,
        }
        with pytest.raises(BeingSnapshotIncompleteException):
            dict_to_snapshot(bad)


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
        # 日本語 identity がそのまま入る (ensure_ascii=False の効果)。
        assert "アダ" in raw
        assert data["snapshot_version"] == 2

    def test_value_raises_type_error(self, tmp_path: Path) -> None:
        """型違反は TypeError。"""
        gateway = BeingSnapshotFileGateway()
        with pytest.raises(TypeError):
            gateway.write("bad", tmp_path / "x.json")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            gateway.read("string-not-path")  # type: ignore[arg-type]
