"""``RestoreBeingSnapshotFromFileUseCase`` — JSON ファイルから Being + memory 状態を復元する。

Phase 5 (Issue #470): run 途中再開 (mid-run resume) milestone のもう片側。
``CaptureBeingSnapshotToFileUseCase`` で出力した JSON を別 / 同プロセスに
読み込んで状態を完全復元する。

責務 (流れ):

1. ``BeingSnapshotFileGateway.read(input_path)`` で ``BeingSnapshot`` を再構築
2. ``BeingRepository.save_snapshot(snapshot)`` で Being を repo に登録
3. ``snapshot.has_memory_payload`` なら ``BeingMemorySnapshotService.restore``
   で 5 store を書き戻す

atomicity 制約は ``BeingPersistenceService.load`` と同じ:
- snapshot 自体の保存は ``BeingRepository.save_snapshot`` の atomic
- memory restore は store ごとに順次 (= 設計判断 #15)
- 失敗時は例外が呼出側 (= CLI) に伝播 (silent failure 禁止)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
)
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotVersionException,
)
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_snapshot_codec import (
    BeingSnapshotCodec,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class RestoreBeingSnapshotResult:
    """restore 完了の報告。"""

    being_id: BeingId
    input_path: Path
    snapshot_version: int
    memory_restored: bool


class RestoreBeingSnapshotFromFileUseCase:
    """JSON ファイルから Being + memory 状態を復元する use case。"""

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

    def execute(self, input_path: Path) -> RestoreBeingSnapshotResult:
        if not isinstance(input_path, Path):
            raise TypeError(
                f"input_path must be Path, got {type(input_path).__name__}"
            )

        snapshot = self._gateway.read(input_path)
        # Phase 8: schema 進化 (a) 厳格モード — 未サポート ``snapshot_version``
        # を repo に書く前に弾く。``codec.SUPPORTED_VERSIONS`` チェックを使い回す
        # (= 同じ判定基準 = 一貫性)。``BeingSnapshotVersionException`` がそのまま
        # 上に伝播し、partial state を残さない。
        if snapshot.snapshot_version not in BeingSnapshotCodec.SUPPORTED_VERSIONS:
            raise BeingSnapshotVersionException(
                f"snapshot_version={snapshot.snapshot_version} is not supported "
                f"(supported: {sorted(BeingSnapshotCodec.SUPPORTED_VERSIONS)}). "
                f"file={input_path}"
            )
        being_id = BeingId(snapshot.being_id_value)

        # 順序: snapshot を repo に書く先に、memory restore を行うと「Being が
        # まだ repo に居ない状態で memory が復元される」逆転が起きる。逆に
        # 「memory 復元失敗 → repo にだけ snapshot が残る」のも好ましくないが、
        # 設計判断 #15 (= store 跨ぎ atomicity なし) で許容済。silent failure
        # は禁止 (= 例外を上位に伝播)。
        self._repo.save_snapshot(snapshot)
        memory_restored = False
        if snapshot.has_memory_payload:
            # defensive: ``BeingSnapshot.__post_init__`` の不変条件で
            # has_memory_payload=True かつ memory_payload_json=None の状態は
            # 構造的に排除されているはず。万一到達したら明示エラーで止める
            # (-O フラグ対策 = assert を使わない)。
            payload = snapshot.memory_payload_json
            if payload is None:
                raise RuntimeError(
                    "has_memory_payload=True なのに memory_payload_json が None: "
                    f"being_id={being_id.value!r} (BeingSnapshot 不変条件違反)"
                )
            self._memory.restore(being_id, payload)
            memory_restored = True

        return RestoreBeingSnapshotResult(
            being_id=being_id,
            input_path=input_path,
            snapshot_version=snapshot.snapshot_version,
            memory_restored=memory_restored,
        )


__all__ = [
    "RestoreBeingSnapshotFromFileUseCase",
    "RestoreBeingSnapshotResult",
]
