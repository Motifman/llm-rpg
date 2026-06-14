"""BeingPersistenceService — Being aggregate + 5 memory store を 1 つの save/load に束ねる。

Phase 4 Step 4-3 (Issue #470): Phase 5 で実装する run 途中再開
(mid-run resume) の use case が叩く統合層。Being の identity / attachment /
declared_memory_kinds と、5 memory store (memo / semantic / memory_link /
recall_buffer / reinterpretation_journal / episodic_episode) の状態を、
**1 回の API 呼び出し** で save / load できるようにする。

## 内部の流れ

### save(being)

1. ``BeingMemorySnapshotService.capture(being.being_id)`` で memory payload (JSON)
   を生成
2. ``BeingSnapshotCodec.encode(being, memory_payload_json=...)`` で v2 snapshot
   を構築
3. ``BeingRepository.save_snapshot(snapshot)`` で永続化

### load(being_id)

1. ``BeingRepository.find_snapshot_by_id(being_id)`` で snapshot を取得
   (見つからなければ ``None`` を返す)
2. ``BeingSnapshotCodec.decode(snapshot)`` で Being aggregate を復元
3. ``snapshot.memory_payload_json`` があれば
   ``BeingMemorySnapshotService.restore(being_id, payload)`` で 5 store に
   書き戻す

## 設計判断

- 「Being save = memory も一緒に save」「Being load = memory も一緒に load」が
  デフォルト挙動。memory なしで save/load したいケース (= 初期化時など) は
  従来通り ``BeingRepository.save / find_by_id`` を直接呼べばよい
- atomicity: capture / encode / save_snapshot は順に直列実行。snapshot save が
  失敗したら memory は再 read されるだけなので run-time に悪影響なし。逆に
  restore は ``BeingMemorySnapshotService.restore`` の store 跨ぎ atomicity
  なしの制限がそのまま伝播する (= 設計判断 #15 と整合)
- 本 service は thin orchestrator。新しい不変条件は導入しない (= silent
  failure は依存先で raise されれば素通しで上位に伝播)
"""

from __future__ import annotations

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.domain.being.aggregate.being import Being
from ai_rpg_world.domain.being.repository.being_repository import BeingRepository
from ai_rpg_world.domain.being.service.being_snapshot_codec import BeingSnapshotCodec
from ai_rpg_world.domain.being.value_object.being_id import BeingId


class BeingPersistenceService:
    """Being aggregate + memory payload を 1 単位で save / load するアプリケーションサービス。"""

    def __init__(
        self,
        *,
        being_repository: BeingRepository,
        memory_snapshot_service: BeingMemorySnapshotService,
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
        self._being_repo = being_repository
        self._memory = memory_snapshot_service

    def save(self, being: Being) -> None:
        """Being aggregate と memory store 群を 1 単位で永続化する。

        ``BeingSnapshot v2`` (= memory payload 込み) として
        ``BeingRepository.save_snapshot`` を呼ぶ。
        """
        if not isinstance(being, Being):
            raise TypeError(f"being must be Being, got {type(being).__name__}")
        memory_payload_json = self._memory.capture(being.being_id)
        snapshot = BeingSnapshotCodec.encode(
            being, memory_payload_json=memory_payload_json
        )
        self._being_repo.save_snapshot(snapshot)

    def load(self, being_id: BeingId) -> Being | None:
        """Being aggregate を読み出し、memory payload があれば 5 store に復元する。

        snapshot が見つからなければ ``None`` を返す (= memory restore も行わない)。
        snapshot に payload が無い (v1 snapshot や payload=None v2) 場合は
        memory restore はスキップする。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError(
                f"being_id must be BeingId, got {type(being_id).__name__}"
            )
        snapshot = self._being_repo.find_snapshot_by_id(being_id)
        if snapshot is None:
            return None
        being = BeingSnapshotCodec.decode(snapshot)
        if snapshot.has_memory_payload:
            # payload が None なら復元不要 (= snapshot 取った時点で memory が空)。
            # has_memory_payload の実装が将来変わった場合の silent failure を
            # 防ぐため、assert ではなく明示的なエラーで弾く (= -O フラグで
            # 落とされない)。
            payload = snapshot.memory_payload_json
            if payload is None:
                raise RuntimeError(
                    f"has_memory_payload=True なのに memory_payload_json が None: "
                    f"being_id={being_id.value!r} (BeingSnapshot 不変条件違反)"
                )
            self._memory.restore(being_id, payload)
        return being


__all__ = ["BeingPersistenceService"]
