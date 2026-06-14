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

    def test_round_trip_で_等価な_snapshot_が返る(self) -> None:
        original = _snapshot()
        restored = dict_to_snapshot(snapshot_to_dict(original))
        assert restored == original

    def test_payload_None_でも_round_trip_できる(self) -> None:
        original = _snapshot(memory_payload_json=None)
        assert dict_to_snapshot(snapshot_to_dict(original)) == original

    def test_非_BeingSnapshot_は_TypeError(self) -> None:
        with pytest.raises(TypeError):
            snapshot_to_dict({"not": "snapshot"})  # type: ignore[arg-type]

    def test_dict_でないと_TypeError(self) -> None:
        with pytest.raises(TypeError):
            dict_to_snapshot("bad")  # type: ignore[arg-type]

    def test_不完全な_dict_は_BeingSnapshot_不変条件で弾かれる(self) -> None:
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

    def test_write_して_read_すると一致する(self, tmp_path: Path) -> None:
        gateway = BeingSnapshotFileGateway()
        snapshot = _snapshot()
        path = tmp_path / "snap.json"
        gateway.write(snapshot, path)
        assert gateway.read(path) == snapshot

    def test_書き出した_JSON_は_human_readable_な_dict(self, tmp_path: Path) -> None:
        """ensure_ascii=False + indent=2 で読みやすい形式。"""
        gateway = BeingSnapshotFileGateway()
        path = tmp_path / "snap.json"
        gateway.write(_snapshot(), path)
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        # 日本語 identity がそのまま入る (ensure_ascii=False の効果)。
        assert "アダ" in raw
        assert data["snapshot_version"] == 2

    def test_型違反は_TypeError(self, tmp_path: Path) -> None:
        gateway = BeingSnapshotFileGateway()
        with pytest.raises(TypeError):
            gateway.write("bad", tmp_path / "x.json")  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            gateway.read("string-not-path")  # type: ignore[arg-type]
