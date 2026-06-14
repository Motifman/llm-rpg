"""ExperimentSnapshotSession — 実験 runner と Phase 4-5 snapshot 機構を結ぶ薄い orchestrator。

Phase 6 (Issue #470): ``scripts/run_scenario_experiment.py`` が
``LlmAgentWiringResult`` から直接 snapshot を取れるようにする統合層。

## 責務

1. ``LlmAgentWiringResult`` から 5 memory store + being_repository を取り出し、
   ``BeingMemorySnapshotService`` と ``CaptureBeingSnapshotToFileUseCase`` /
   ``RestoreBeingSnapshotFromFileUseCase`` を組み立てる
2. runtime の player_ids を ``BeingAttachmentResolver`` で being_id に変換
3. 全 player について capture / restore を順に呼ぶ
4. 失敗は logger.warning に残しつつ 1 件失敗で全体が止まらないようにする
   (= **save 失敗で実験 run 自体は壊さない** = 設計判断の核)

## 設計判断

- 「run 終了後に snapshot を取るだけ」と「run 開始前に snapshot を読むだけ」を
  別メソッドに分離し、副作用の発生タイミングを呼出側 (= runner) が制御できる
  ようにする
- snapshot file のレイアウト: ``<dir>/<being_id>.json`` (1 Being = 1 file)。
  CLI と互換 (= ``scripts/being_snapshot_cli.py`` で個別に処理可能)
- ``capture_all`` は **全 player を順に処理し、各失敗は単独 warning** とする。
  「ある player の memo が壊れている → 他の player の snapshot を諦める」
  を避けるため (= 実験データの最大救済)
- ``restore_all`` は逆に **1 つでも失敗したら例外** にする (= 中途半端な
  状態で experiment を始めない fail-fast)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
)
from ai_rpg_world.application.being.capture_being_snapshot_to_file_use_case import (
    BeingNotFoundForSnapshotError,
    CaptureBeingSnapshotToFileUseCase,
)
from ai_rpg_world.application.being.restore_being_snapshot_from_file_use_case import (
    RestoreBeingSnapshotFromFileUseCase,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.world_id import (
    DEFAULT_SINGLE_WORLD_ID,
    WorldId,
)

logger = logging.getLogger(__name__)


def _empty_memo_store() -> Any:
    from ai_rpg_world.application.llm.services.in_memory_memo_store import (
        InMemoryMemoStore,
    )

    return InMemoryMemoStore()


def _empty_semantic_store() -> Any:
    from ai_rpg_world.application.llm.services.in_memory_semantic_memory_store import (
        InMemorySemanticMemoryStore,
    )

    return InMemorySemanticMemoryStore()


def _empty_memory_link_store() -> Any:
    from ai_rpg_world.application.llm.services.in_memory_episodic_memory_link_store import (
        InMemoryMemoryLinkStore,
    )

    return InMemoryMemoryLinkStore()


def _empty_recall_buffer_store() -> Any:
    from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
        InMemoryEpisodicRecallBufferStore,
    )

    return InMemoryEpisodicRecallBufferStore()


def _empty_journal_store() -> Any:
    from ai_rpg_world.application.llm.services.in_memory_episodic_reinterpretation_stores import (
        InMemoryEpisodicReinterpretationJournalStore,
    )

    return InMemoryEpisodicReinterpretationJournalStore()


def _empty_episode_store() -> Any:
    from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
        InMemorySubjectiveEpisodeStore,
    )

    return InMemorySubjectiveEpisodeStore()


@dataclass(frozen=True)
class _PlayerSnapshotMapping:
    """1 player ↔ 1 file のマッピング。"""

    player_id: PlayerId
    being_id: BeingId
    file_path: Path


@dataclass(frozen=True)
class CaptureAllReport:
    """``capture_all`` の集計レポート。"""

    succeeded: list[BeingId]
    failed: list[tuple[BeingId, str]]  # (being_id, error message)

    @property
    def is_clean(self) -> bool:
        """全 player が成功した場合のみ True。"""
        return not self.failed


@dataclass(frozen=True)
class RestoreAllReport:
    """``restore_all`` の集計レポート。"""

    restored: list[BeingId]


class ExperimentSnapshotSession:
    """experiment runner からみた snapshot 操作の入口。

    1 つの runtime / wiring に対して 1 つ作る。``capture_all`` / ``restore_all``
    のみが副作用を持つ。
    """

    def __init__(
        self,
        *,
        wiring_result: Any,
        snapshot_dir: Path,
        world_id: WorldId | None = None,
    ) -> None:
        # **必須** store: 「これがなければ snapshot 自体が意味を持たない」もの。
        # being_repository / resolver はないと that's that.
        required_fields = ("being_repository", "being_attachment_resolver")
        missing_required = [
            name
            for name in required_fields
            if getattr(wiring_result, name, None) is None
        ]
        if missing_required:
            raise RuntimeError(
                "wiring_result is missing required handle(s) for snapshot: "
                f"{missing_required}."
            )

        # 任意 store: 「未配線なら空 in-memory store で代用」する。escape_game
        # runtime のように semantic / memory_link / recall_buffer / journal を
        # 使わない構成でも snapshot を取れるようにするため (= 空の payload に
        # なるが file の整合性は保たれる)。memo / episode は普段使うので強く
        # 期待するが、None でも fallback できる方が安全。
        memo_store = wiring_result.memo_store or _empty_memo_store()
        semantic_store = (
            wiring_result.semantic_memory_store or _empty_semantic_store()
        )
        memory_link_store = (
            wiring_result.memory_link_store or _empty_memory_link_store()
        )
        recall_buffer_store = (
            wiring_result.episodic_recall_buffer_store
            or _empty_recall_buffer_store()
        )
        journal_store = (
            wiring_result.episodic_reinterpretation_journal_store
            or _empty_journal_store()
        )
        episode_store = (
            wiring_result.episodic_episode_store or _empty_episode_store()
        )

        # どの store が空 fallback で稼働しているかを 1 度だけ info ログに残す
        # = 「snapshot 取ったけど semantic は空だった」のデバッグ材料。
        fallback_used = [
            name
            for name in (
                "memo_store",
                "semantic_memory_store",
                "memory_link_store",
                "episodic_recall_buffer_store",
                "episodic_reinterpretation_journal_store",
                "episodic_episode_store",
            )
            if getattr(wiring_result, name, None) is None
        ]
        if fallback_used:
            logger.info(
                "snapshot session: using empty in-memory fallback for stores: %s "
                "(wiring did not expose these; payload entries will be empty)",
                fallback_used,
            )

        self._memory_snapshot = BeingMemorySnapshotService(
            memo_store=memo_store,
            semantic_store=semantic_store,
            memory_link_store=memory_link_store,
            recall_buffer_store=recall_buffer_store,
            reinterpretation_journal_store=journal_store,
            episodic_episode_store=episode_store,
        )
        self._gateway = BeingSnapshotFileGateway()
        self._capture_use_case = CaptureBeingSnapshotToFileUseCase(
            being_repository=wiring_result.being_repository,
            memory_snapshot_service=self._memory_snapshot,
            file_gateway=self._gateway,
        )
        self._restore_use_case = RestoreBeingSnapshotFromFileUseCase(
            being_repository=wiring_result.being_repository,
            memory_snapshot_service=self._memory_snapshot,
            file_gateway=self._gateway,
        )
        self._resolver = wiring_result.being_attachment_resolver
        self._snapshot_dir = snapshot_dir
        self._world_id = world_id or DEFAULT_SINGLE_WORLD_ID

    @property
    def snapshot_dir(self) -> Path:
        return self._snapshot_dir

    def file_path_for(self, being_id: BeingId) -> Path:
        """``being_id`` の snapshot file path を返す。"""
        return self._snapshot_dir / f"{being_id.value}.json"

    def _resolve_player_being_ids(
        self, player_ids: Sequence[PlayerId]
    ) -> list[_PlayerSnapshotMapping]:
        """``player_ids`` を ``(player_id, being_id, file_path)`` に変換する。

        attach されていない player は warning ログを出してスキップ。
        """
        out: list[_PlayerSnapshotMapping] = []
        for pid in player_ids:
            being_id = self._resolver.resolve_being_id(self._world_id, pid)
            if being_id is None:
                logger.warning(
                    "no being attached to player_id=%s in world=%s; "
                    "skipping snapshot for this player",
                    pid.value,
                    self._world_id.value,
                )
                continue
            out.append(
                _PlayerSnapshotMapping(
                    player_id=pid,
                    being_id=being_id,
                    file_path=self.file_path_for(being_id),
                )
            )
        return out

    def capture_all(
        self, player_ids: Sequence[PlayerId]
    ) -> CaptureAllReport:
        """全 player の Being snapshot を ``snapshot_dir`` 配下に書き出す。

        各 player の失敗は warning に残しつつ続行 (= 全体が止まらない)。
        実験 run のデータ救済を最優先する設計。
        """
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        mappings = self._resolve_player_being_ids(player_ids)
        succeeded: list[BeingId] = []
        failed: list[tuple[BeingId, str]] = []
        for m in mappings:
            try:
                self._capture_use_case.execute(m.being_id, m.file_path)
                succeeded.append(m.being_id)
                logger.info(
                    "snapshot captured: being_id=%s file=%s",
                    m.being_id.value,
                    m.file_path,
                )
            except BeingNotFoundForSnapshotError as exc:
                logger.warning(
                    "snapshot capture failed for being_id=%s: %s",
                    m.being_id.value,
                    exc,
                )
                failed.append((m.being_id, str(exc)))
            except Exception as exc:  # noqa: BLE001 - 実験 run の生命を最優先
                logger.warning(
                    "snapshot capture failed for being_id=%s: %s",
                    m.being_id.value,
                    exc,
                    exc_info=True,
                )
                failed.append((m.being_id, repr(exc)))
        return CaptureAllReport(succeeded=succeeded, failed=failed)

    def restore_all_from_dir(self, input_dir: Path) -> RestoreAllReport:
        """``input_dir`` 配下の ``*.json`` を全て restore する。

        1 件でも失敗したら例外 (= partial state で experiment を始めない
        fail-fast)。ファイルがゼロ件なら no-op で空 report を返す。
        """
        if not input_dir.exists():
            raise FileNotFoundError(
                f"snapshot dir does not exist: {input_dir}"
            )
        if not input_dir.is_dir():
            raise NotADirectoryError(f"not a directory: {input_dir}")

        # ファイル名順で読み込む = 決定的な順序にする (= 復元が冪等)。
        files = sorted(p for p in input_dir.iterdir() if p.suffix == ".json")
        restored: list[BeingId] = []
        for path in files:
            result = self._restore_use_case.execute(path)
            restored.append(result.being_id)
            logger.info(
                "snapshot restored: being_id=%s file=%s memory_restored=%s",
                result.being_id.value,
                path,
                result.memory_restored,
            )
        return RestoreAllReport(restored=restored)


__all__ = [
    "ExperimentSnapshotSession",
    "CaptureAllReport",
    "RestoreAllReport",
]
