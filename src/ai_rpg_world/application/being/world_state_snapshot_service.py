"""``WorldStateSnapshotService`` — runtime ↔ ``WorldStateSnapshot`` の変換。

Phase 9-1 (Issue #470): **器だけ** 用意した skeleton。capture / restore とも
現状は subsystems 空で素通す。Phase 9-2 以降で 1 subsystem ずつ実装を埋める。

## subsystem 登録の仕組み

将来 subsystem を増やすときは ``WorldSubsystemCodec`` を継承した実装を
``WorldStateSnapshotService`` に登録する。Phase 9-1 は登録ゼロでスタート
(= subsystems 辞書が空のまま回る)。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from ai_rpg_world.application.being.world_state_snapshot import (
    SUPPORTED_WORLD_SNAPSHOT_VERSIONS,
    WorldStateScenarioMismatchError,
    WorldStateSnapshot,
    WorldStateSnapshotVersionError,
)

logger = logging.getLogger(__name__)


class WorldSubsystemCodec(ABC):
    """1 つの world subsystem (= player_status / spot_interior 等) の
    capture / restore を担当する抽象。

    Phase 9-2 以降で各 subsystem について本 ABC を継承した実装を追加する。
    """

    @property
    @abstractmethod
    def subsystem_key(self) -> str:
        """``subsystems`` dict 内の key (= "player_status" 等の安定識別子)。"""

    @abstractmethod
    def capture(self, runtime: Any) -> dict[str, Any]:
        """runtime から subsystem state を JSON-serializable dict に変換。"""

    @abstractmethod
    def restore(self, runtime: Any, data: dict[str, Any]) -> None:
        """``data`` を runtime に書き戻す。"""


class WorldStateSnapshotService:
    """runtime ↔ WorldStateSnapshot の変換を担うサービス。

    capture / restore とも、登録された ``WorldSubsystemCodec`` を順次呼ぶ。
    """

    def __init__(
        self,
        *,
        subsystem_codecs: list[WorldSubsystemCodec] | None = None,
    ) -> None:
        codecs = list(subsystem_codecs or [])
        # 重複検出 (= 同じ subsystem_key を 2 つ登録するのは設計バグ)
        seen: set[str] = set()
        for codec in codecs:
            key = codec.subsystem_key
            if key in seen:
                raise ValueError(
                    f"duplicate subsystem_key in codecs: {key!r}"
                )
            seen.add(key)
        self._codecs: list[WorldSubsystemCodec] = codecs

    def capture(
        self,
        runtime: Any,
        *,
        source_scenario: str,
        world_tick: int,
        captured_at: str | None = None,
    ) -> WorldStateSnapshot:
        """runtime から WorldStateSnapshot を構築する。

        各 subsystem codec の ``capture`` を呼び、結果を subsystems dict に
        詰める。1 つでも失敗すれば例外 (= partial world snapshot を作らない
        = silent failure を構造で防ぐ)。
        """
        subsystems: dict[str, dict[str, Any]] = {}
        for codec in self._codecs:
            data = codec.capture(runtime)
            if not isinstance(data, dict):
                raise TypeError(
                    f"subsystem {codec.subsystem_key!r} capture must return "
                    f"dict, got {type(data).__name__}"
                )
            subsystems[codec.subsystem_key] = data
        return WorldStateSnapshot(
            source_scenario=source_scenario,
            world_tick=world_tick,
            subsystems=subsystems,
            captured_at=captured_at,
        )

    def restore(
        self,
        runtime: Any,
        snapshot: WorldStateSnapshot,
        *,
        current_scenario: str,
    ) -> None:
        """WorldStateSnapshot を runtime に書き戻す。

        - ``schema_version`` が未サポートなら ``WorldStateSnapshotVersionError``
        - ``source_scenario != current_scenario`` なら
          ``WorldStateScenarioMismatchError`` (= fail-fast)
        - 1 subsystem の codec も登録されていない subsystem は無視 (= 後方
          互換: 新 version で増えた subsystem を旧 code で読む場合の救済)
        - 各 subsystem の restore は順次。失敗時は例外伝播 (= partial state
          を runtime に残さない方針)
        """
        if snapshot.schema_version not in SUPPORTED_WORLD_SNAPSHOT_VERSIONS:
            raise WorldStateSnapshotVersionError(
                f"world snapshot schema_version={snapshot.schema_version} "
                f"is not supported "
                f"(supported: {sorted(SUPPORTED_WORLD_SNAPSHOT_VERSIONS)})"
            )
        if snapshot.source_scenario != current_scenario:
            raise WorldStateScenarioMismatchError(
                f"world snapshot source_scenario={snapshot.source_scenario!r} "
                f"does not match current_scenario={current_scenario!r}. "
                f"world state is scenario-specific (spot_id / item_spec / "
                f"events are tied to scenario), refusing to load."
            )

        # 登録済 codec を順次呼ぶ。snapshot 側に登録外の subsystem がある場合
        # は info ログを残して skip (= 後方互換性)。
        codec_by_key = {c.subsystem_key: c for c in self._codecs}
        for key, data in snapshot.subsystems.items():
            codec = codec_by_key.get(key)
            if codec is None:
                logger.info(
                    "world snapshot has subsystem %r but no codec registered; "
                    "skipping (= forward compatibility)",
                    key,
                )
                continue
            codec.restore(runtime, data)

    @property
    def registered_subsystem_keys(self) -> list[str]:
        """登録済 subsystem の key 一覧 (= 主に test / debug 用)。"""
        return [c.subsystem_key for c in self._codecs]


__all__ = [
    "WorldStateSnapshotService",
    "WorldSubsystemCodec",
]
