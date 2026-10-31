"""``RestoreBeingSnapshotFromFileUseCase`` — JSON ファイルから Being + memory 状態を復元する。

Phase 5 (Issue #470): run 途中再開 (mid-run resume) milestone のもう片側。
``CaptureBeingSnapshotToFileUseCase`` で出力した JSON を別 / 同プロセスに
読み込んで状態を完全復元する。

責務 (流れ):

1. ``BeingSnapshotFileGateway.read(input_path)`` で ``BeingSnapshot`` を再構築
2. ``BeingRepository.save_snapshot(snapshot)`` で Being を repo に登録
3. ``snapshot.has_memory_payload`` なら、消した部品の欄を捨ててから
   ``BeingMemorySnapshotService.restore`` で store に書き戻す

atomicity 制約:
- snapshot 自体の保存は ``BeingRepository.save_snapshot`` の atomic
- memory restore は store ごとに順次 (= 設計判断 #15)
- 失敗時は例外が呼出側 (= CLI) に伝播 (silent failure 禁止)
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
)
from ai_rpg_world.application.being.removed_memory_payload_keys import (
    drop_removed_memory_payload_keys,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.domain.being.exception.being_exceptions import (
    BeingSnapshotIncompleteException,
    BeingSnapshotVersionException,
)
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_snapshot_codec import (
    BeingSnapshotCodec,
)
from ai_rpg_world.domain.being.value_object.being_snapshot import BeingSnapshot


@dataclass(frozen=True)
class RestoreBeingSnapshotResult:
    """restore 完了の報告。"""

    being_id: BeingId
    input_path: Path
    snapshot_version: int
    memory_restored: bool
    removed_memory_key_counts: dict[str, int] = field(default_factory=dict)
    removed_declared_memory_kind_counts: dict[str, int] = field(default_factory=dict)
    #: ``persona`` の無い古い snapshot から読み捨てた名前と一人称 (``name`` と ``first_person``)。読み捨てなければ None。
    removed_legacy_identity: dict[str, str | None] | None = None
    #: 古い snapshot に残る、Being が動かしていた世界とプレイヤーの番号。対応表の欄が無い古い世界の snapshot から
    #: 対応表を作り直すのに使う (design_decisions D1928、D1928-2)。今の形の snapshot には無い。
    legacy_attachment_world_id: int | None = None
    legacy_attachment_player_id: int | None = None


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
            raise TypeError(f"being_repository must be BeingRepository, got {type(being_repository).__name__}")
        if not isinstance(memory_snapshot_service, BeingMemorySnapshotService):
            raise TypeError(
                "memory_snapshot_service must be BeingMemorySnapshotService, "
                f"got {type(memory_snapshot_service).__name__}"
            )
        if not isinstance(file_gateway, BeingSnapshotFileGateway):
            raise TypeError(f"file_gateway must be BeingSnapshotFileGateway, got {type(file_gateway).__name__}")
        self._repo = being_repository
        self._memory = memory_snapshot_service
        self._gateway = file_gateway

    def execute(
        self,
        input_path: Path,
    ) -> RestoreBeingSnapshotResult:
        if not isinstance(input_path, Path):
            raise TypeError(f"input_path must be Path, got {type(input_path).__name__}")

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
        removed_legacy_identity: dict[str, str | None] | None = None
        if snapshot.has_legacy_identity:
            removed_legacy_identity = {
                "name": snapshot.legacy_identity_name,
                "first_person": snapshot.legacy_identity_first_person,
            }
            snapshot = self._with_current_persona(snapshot)
        being_id = BeingSnapshotCodec.decode(snapshot).being_id
        removed_declared_memory_kind_counts = BeingSnapshotCodec.removed_declared_memory_kind_counts(snapshot)
        legacy_world_id, legacy_player_id = snapshot.legacy_attachment_world_id, snapshot.legacy_attachment_player_id
        snapshot = replace(
            snapshot, legacy_declared_memory_kinds=(), legacy_attachment_world_id=None, legacy_attachment_player_id=None
        )

        payload: str | None = None
        removed_memory_key_counts: dict[str, int] = {}
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
            payload, removed_memory_key_counts = drop_removed_memory_payload_keys(payload)

        # 順序: snapshot を repo に書く先に、memory restore を行うと「Being が
        # まだ repo に居ない状態で memory が復元される」逆転が起きる。逆に
        # 「memory 復元失敗 → repo にだけ snapshot が残る」のも好ましくないが、
        # 設計判断 #15 (= store 跨ぎ atomicity なし) で許容済。silent failure
        # は禁止 (= 例外を上位に伝播)。
        self._repo.save_snapshot(snapshot)
        memory_restored = False
        if payload is not None:
            self._memory.restore(being_id, payload)
            memory_restored = True

        return RestoreBeingSnapshotResult(
            being_id=being_id,
            input_path=input_path,
            snapshot_version=snapshot.snapshot_version,
            memory_restored=memory_restored,
            removed_memory_key_counts=removed_memory_key_counts,
            removed_declared_memory_kind_counts=removed_declared_memory_kind_counts,
            removed_legacy_identity=removed_legacy_identity,
            legacy_attachment_world_id=legacy_world_id,
            legacy_attachment_player_id=legacy_player_id,
        )

    def _with_current_persona(self, snapshot: BeingSnapshot) -> BeingSnapshot:
        """古い snapshot の仮の名前と一人称は使わず、起動時にシナリオから入れた人柄で埋める (design_decisions D1469-2)。"""
        current = self._repo.find_by_id(BeingId(snapshot.being_id_value))
        if current is None:
            raise BeingSnapshotIncompleteException(
                f"snapshot of {snapshot.being_id_value!r} has no persona and no Being to take it from; "
                "provision the Being from the scenario before restoring an old snapshot"
            )
        return replace(snapshot, persona=current.persona, legacy_identity_name=None, legacy_identity_first_person=None)


__all__ = [
    "RestoreBeingSnapshotFromFileUseCase",
    "RestoreBeingSnapshotResult",
]
