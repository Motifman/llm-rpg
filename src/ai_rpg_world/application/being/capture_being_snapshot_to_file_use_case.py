"""``CaptureBeingSnapshotToFileUseCase`` — 現在の Being + memory 状態を JSON ファイルに書き出す。

Phase 5 (Issue #470): run 途中再開 (mid-run resume) milestone の入口。
LLM agent のターン処理を一時停止して状態をファイルに書き出し、後で
``RestoreBeingSnapshotFromFileUseCase`` で同 / 別プロセスに復元できる。

責務 (流れ):

1. ``BeingRepository.find_by_id(being_id)`` で Being aggregate を引く
2. ``BeingMemorySnapshotService.capture(being_id)`` で memory payload JSON
   を生成
3. ``BeingSnapshotCodec.encode(being, memory_payload_json=...)`` で v2 snapshot
4. ``BeingSnapshotFileGateway.write(snapshot, output_path)`` で書き出し

副作用は **ファイル書き込みのみ** (= memory store / repo は読むだけ)。
これで「snapshot を取るだけ」のオペレーションが安全に走る。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
    BeingSnapshotFileMetadata,
)
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_snapshot_codec import BeingSnapshotCodec
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class BeingNotFoundForSnapshotError(Exception):
    """指定 ``BeingId`` の Being が repository に存在しない。"""


@dataclass(frozen=True)
class CaptureBeingSnapshotResult:
    """capture 完了の報告。"""

    being_id: BeingId
    output_path: Path
    snapshot_version: int
    has_memory_payload: bool


class CaptureBeingSnapshotToFileUseCase:
    """Being + memory 状態を JSON ファイルにエクスポートする use case。"""

    def __init__(
        self,
        *,
        being_repository: BeingRepository,
        memory_snapshot_service: BeingMemorySnapshotService,
        file_gateway: BeingSnapshotFileGateway,
    ) -> None:
        if not isinstance(being_repository, BeingRepository):
            raise TypeError(
                "being_repository must be BeingRepository, "
                f"got {type(being_repository).__name__}"
            )
        if not isinstance(memory_snapshot_service, BeingMemorySnapshotService):
            raise TypeError(
                "memory_snapshot_service must be BeingMemorySnapshotService, "
                f"got {type(memory_snapshot_service).__name__}"
            )
        if not isinstance(file_gateway, BeingSnapshotFileGateway):
            raise TypeError(
                "file_gateway must be BeingSnapshotFileGateway, "
                f"got {type(file_gateway).__name__}"
            )
        self._repo = being_repository
        self._memory = memory_snapshot_service
        self._gateway = file_gateway

    def execute(
        self,
        being_id: BeingId,
        output_path: Path,
        *,
        metadata: BeingSnapshotFileMetadata | None = None,
    ) -> CaptureBeingSnapshotResult:
        """snapshot を取得してファイルに書き出す。

        Phase 7 (Issue #470): ``metadata`` を渡せば snapshot file の
        ``_metadata`` ブロックに ``source_scenario`` / ``captured_at`` 等を
        埋め込める。cross-scenario transfer 検知用。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        if not isinstance(output_path, Path):
            raise TypeError(
                f"output_path must be Path, got {type(output_path).__name__}"
            )

        being = self._repo.find_by_id(being_id)
        if being is None:
            raise BeingNotFoundForSnapshotError(
                f"being not found in repository: being_id={being_id.value!r}"
            )

        memory_payload_json = self._memory.capture(being_id)
        snapshot = BeingSnapshotCodec.encode(
            being, memory_payload_json=memory_payload_json
        )
        self._gateway.write(snapshot, output_path, metadata=metadata)
        return CaptureBeingSnapshotResult(
            being_id=being_id,
            output_path=output_path,
            snapshot_version=snapshot.snapshot_version,
            has_memory_payload=snapshot.has_memory_payload,
        )


__all__ = [
    "CaptureBeingSnapshotToFileUseCase",
    "CaptureBeingSnapshotResult",
    "BeingNotFoundForSnapshotError",
]
