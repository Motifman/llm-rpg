"""``BeingSnapshot`` ↔ JSON ファイル の I/O 抽象。

Phase 5 (Issue #470): ``CaptureBeingSnapshotToFileUseCase`` /
``RestoreBeingSnapshotFromFileUseCase`` がファイル経由で snapshot を入出力
するための薄い gateway。

なぜ別 module:
- use case が ``open()`` / ``json.dump`` の生 API に直接依存しないようにする
  (= テストで gateway を mock 化できる / ファイル形式を 1 箇所に集約)
- ``_snapshot_to_payload_dict`` 同等のシリアライズ責務 (Phase 4-1) を
  application 層に持つことで、CLI から呼ぶときの infra 依存を最小化
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot


def snapshot_to_dict(snapshot: BeingSnapshot) -> dict[str, Any]:
    """``BeingSnapshot`` を JSON 互換 dict に変換する。

    sqlite_being_repository の ``_snapshot_to_payload_dict`` と同形式
    (= 同じ JSON が repo / file 両方で読める)。
    """
    if not isinstance(snapshot, BeingSnapshot):
        raise TypeError(
            f"snapshot must be BeingSnapshot, got {type(snapshot).__name__}"
        )
    return {
        "being_id_value": snapshot.being_id_value,
        "identity_name": snapshot.identity_name,
        "identity_first_person": snapshot.identity_first_person,
        "attachment_world_id": snapshot.attachment_world_id,
        "attachment_player_id": snapshot.attachment_player_id,
        "declared_memory_kinds": list(snapshot.declared_memory_kinds),
        "snapshot_version": snapshot.snapshot_version,
        "memory_payload_json": snapshot.memory_payload_json,
    }


def dict_to_snapshot(data: dict[str, Any]) -> BeingSnapshot:
    """JSON 由来 dict から ``BeingSnapshot`` を再構築する。

    ``BeingSnapshot.__post_init__`` の構造検証 (= all-or-nothing) はそのまま
    走る = 不完全な入力は ``BeingSnapshotIncompleteException`` で弾かれる。
    """
    if not isinstance(data, dict):
        raise TypeError(f"data must be dict, got {type(data).__name__}")
    raw_kinds = data.get("declared_memory_kinds", [])
    if not isinstance(raw_kinds, list):
        raise TypeError(
            f"declared_memory_kinds must be list, got {type(raw_kinds).__name__}"
        )
    return BeingSnapshot(
        being_id_value=str(data["being_id_value"]),
        identity_name=str(data["identity_name"]),
        identity_first_person=str(data["identity_first_person"]),
        attachment_world_id=data.get("attachment_world_id"),
        attachment_player_id=data.get("attachment_player_id"),
        declared_memory_kinds=tuple(str(x) for x in raw_kinds),
        snapshot_version=int(data.get("snapshot_version", 1)),
        memory_payload_json=data.get("memory_payload_json"),
    )


class BeingSnapshotFileGateway:
    """``BeingSnapshot`` をローカルファイルに読み書きする gateway。

    テスト用には別実装 (``InMemoryBeingSnapshotFileGateway`` 等) を作って
    差し替え可能。
    """

    def write(self, snapshot: BeingSnapshot, output_path: Path) -> None:
        """``snapshot`` を ``output_path`` に JSON で書き出す。

        親ディレクトリは事前に存在する想定。``ensure_ascii=False`` で日本語
        identity も読みやすい形で保存する。
        """
        if not isinstance(snapshot, BeingSnapshot):
            raise TypeError(
                f"snapshot must be BeingSnapshot, got {type(snapshot).__name__}"
            )
        if not isinstance(output_path, Path):
            raise TypeError(
                f"output_path must be Path, got {type(output_path).__name__}"
            )
        data = snapshot_to_dict(snapshot)
        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read(self, input_path: Path) -> BeingSnapshot:
        """``input_path`` から JSON を読み、``BeingSnapshot`` を返す。"""
        if not isinstance(input_path, Path):
            raise TypeError(
                f"input_path must be Path, got {type(input_path).__name__}"
            )
        raw = input_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return dict_to_snapshot(data)


__all__ = [
    "BeingSnapshotFileGateway",
    "snapshot_to_dict",
    "dict_to_snapshot",
]
