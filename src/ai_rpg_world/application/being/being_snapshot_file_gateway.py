"""``BeingSnapshot`` ↔ JSON ファイル の I/O 抽象。

Phase 5 (Issue #470): ``CaptureBeingSnapshotToFileUseCase`` /
``RestoreBeingSnapshotFromFileUseCase`` がファイル経由で snapshot を入出力
するための薄い gateway。

なぜ別 module:
- use case が ``open()`` / ``json.dump`` の生 API に直接依存しないようにする
  (= テストで gateway を mock 化できる / ファイル形式を 1 箇所に集約)
- dict との変換は ``domain/being/service/being_snapshot_dict.py`` にあり、SQLite のリポジトリと同じ形で書く

## メタデータ (Phase 7)

snapshot JSON の root には ``_metadata`` キーを追加できる:
- ``source_scenario``: snapshot を取った時のシナリオ名 (= 別シナリオへの
  cross-transfer 検知用、ハードエラーにはしない)
- ``captured_at``: ISO 8601 タイムスタンプ

メタデータは **BeingSnapshot VO とは独立** に管理する (= VO に余計な field
を増やさず、ファイル形式だけで運用情報を持つ)。旧 snapshot (``_metadata``
キーなし) は ``None`` で読み出されるので後方互換。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_rpg_world.domain.being.service.being_snapshot_dict import dict_to_snapshot, snapshot_to_dict
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot


@dataclass(frozen=True)
class BeingSnapshotFileMetadata:
    """snapshot JSON の ``_metadata`` ブロックを表す VO。"""

    source_scenario: str | None = None
    captured_at: str | None = None  # ISO 8601 文字列。Optional で後方互換。

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_scenario": self.source_scenario,
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BeingSnapshotFileMetadata:
        return cls(
            source_scenario=data.get("source_scenario"),
            captured_at=data.get("captured_at"),
        )


class BeingSnapshotFileGateway:
    """``BeingSnapshot`` をローカルファイルに読み書きする gateway。

    テスト用には別実装 (``InMemoryBeingSnapshotFileGateway`` 等) を作って
    差し替え可能。
    """

    _METADATA_KEY = "_metadata"

    def write(
        self,
        snapshot: BeingSnapshot,
        output_path: Path,
        *,
        metadata: BeingSnapshotFileMetadata | None = None,
    ) -> None:
        """``snapshot`` を ``output_path`` に JSON で書き出す。

        親ディレクトリは事前に存在する想定。``ensure_ascii=False`` で日本語
        人柄も読みやすい形で保存する。``metadata`` を渡せば
        ``_metadata`` ブロックも書き込まれる。
        """
        if not isinstance(snapshot, BeingSnapshot):
            raise TypeError(f"snapshot must be BeingSnapshot, got {type(snapshot).__name__}")
        if not isinstance(output_path, Path):
            raise TypeError(f"output_path must be Path, got {type(output_path).__name__}")
        if metadata is not None and not isinstance(metadata, BeingSnapshotFileMetadata):
            raise TypeError(f"metadata must be BeingSnapshotFileMetadata or None, got {type(metadata).__name__}")
        data = snapshot_to_dict(snapshot)
        if metadata is not None:
            data[self._METADATA_KEY] = metadata.to_dict()
        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def read(self, input_path: Path) -> BeingSnapshot:
        """``input_path`` から JSON を読み、``BeingSnapshot`` を返す。"""
        if not isinstance(input_path, Path):
            raise TypeError(f"input_path must be Path, got {type(input_path).__name__}")
        raw = input_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return dict_to_snapshot(data)

    def read_metadata(self, input_path: Path) -> BeingSnapshotFileMetadata | None:
        """``input_path`` から ``_metadata`` ブロックを読む。なければ ``None``。

        Phase 7: 古い snapshot (``_metadata`` キー無し) は ``None`` を返す。
        cross-scenario transfer 検知などに使う。
        """
        if not isinstance(input_path, Path):
            raise TypeError(f"input_path must be Path, got {type(input_path).__name__}")
        raw = input_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        meta = data.get(self._METADATA_KEY)
        if meta is None:
            return None
        if not isinstance(meta, dict):
            return None
        return BeingSnapshotFileMetadata.from_dict(meta)


class WorldStateSnapshotFileGateway:
    """``WorldStateSnapshot`` をローカルファイル (``world.json``) に読み書きする。

    Phase 9-1 (Issue #470): Being snapshot と並列の世界状態 snapshot 用。
    snapshot directory 配下に **1 ファイル固定** (= 全 player 共有なので 1 つ)。
    """

    _FILENAME = "world.json"

    @classmethod
    def file_path_in_dir(cls, snapshot_dir: Path) -> Path:
        """snapshot directory 内の ``world.json`` への path を返す。"""
        if not isinstance(snapshot_dir, Path):
            raise TypeError(f"snapshot_dir must be Path, got {type(snapshot_dir).__name__}")
        return snapshot_dir / cls._FILENAME

    def write(self, snapshot: Any, output_dir: Path) -> Path:
        """``snapshot`` を ``output_dir/world.json`` に書く。返り値は file path。"""
        from ai_rpg_world.application.being.world_state_snapshot import (
            WorldStateSnapshot,
        )

        if not isinstance(snapshot, WorldStateSnapshot):
            raise TypeError(f"snapshot must be WorldStateSnapshot, got {type(snapshot).__name__}")
        if not isinstance(output_dir, Path):
            raise TypeError(f"output_dir must be Path, got {type(output_dir).__name__}")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = self.file_path_in_dir(output_dir)
        path.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def read(self, input_dir: Path) -> Any:
        """``input_dir/world.json`` から ``WorldStateSnapshot`` を返す。

        ファイルが無ければ ``FileNotFoundError`` を投げる。
        """
        from ai_rpg_world.application.being.world_state_snapshot import (
            WorldStateSnapshot,
        )

        if not isinstance(input_dir, Path):
            raise TypeError(f"input_dir must be Path, got {type(input_dir).__name__}")
        path = self.file_path_in_dir(input_dir)
        if not path.exists():
            raise FileNotFoundError(f"world snapshot file not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return WorldStateSnapshot.from_dict(data)

    def exists_in(self, input_dir: Path) -> bool:
        """``input_dir/world.json`` が存在するなら True。"""
        if not isinstance(input_dir, Path):
            raise TypeError(f"input_dir must be Path, got {type(input_dir).__name__}")
        return self.file_path_in_dir(input_dir).exists()


__all__ = [
    "BeingSnapshotFileGateway",
    "WorldStateSnapshotFileGateway",
    "snapshot_to_dict",
    "dict_to_snapshot",
]
