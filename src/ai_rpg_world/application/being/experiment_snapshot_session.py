"""ExperimentSnapshotSession — 実験 runner と Phase 4-5 snapshot 機構を結ぶ薄い orchestrator。

Phase 6 (Issue #470): ``scripts/run_scenario_experiment.py`` が wiring stub
(escape runtime から組む ``_wiring_stub_from_world_runtime`` の返り値) から直接
snapshot を取れるようにする統合層。

## 責務

1. wiring stub から 5 memory store + being_repository を取り出し、
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ai_rpg_world.application.being.being_memory_snapshot_service import (
    BeingMemorySnapshotService,
    SnapshotCoverageError,
)
from ai_rpg_world.application.being.being_snapshot_file_gateway import (
    BeingSnapshotFileGateway,
    BeingSnapshotFileMetadata,
    WorldStateSnapshotFileGateway,
)
from ai_rpg_world.application.being.world_state_snapshot import (
    WorldStateSnapshot,
)
from ai_rpg_world.application.being.world_state_snapshot_service import (
    WorldStateSnapshotService,
    WorldSubsystemCodec,
)
from ai_rpg_world.application.being.world_subsystems import (
    ActionResultStoreSubsystemCodec,
    DayNightSubsystemCodec,
    ItemInstanceSubsystemCodec,
    ObservationBufferSubsystemCodec,
    PendingFoodSpoilageSubsystemCodec,
    PlayerActiveEffectsSubsystemCodec,
    PlayerAttentionLevelSubsystemCodec,
    PlayerGrowthSubsystemCodec,
    PlayerInventorySubsystemCodec,
    PlayerNeedsSubsystemCodec,
    PlayerPositionSubsystemCodec,
    PlayerPursuitStateSubsystemCodec,
    PlayerSpotNavigationStateSubsystemCodec,
    PlayerStateDictSubsystemCodec,
    PlayerVitalsSubsystemCodec,
    ScenarioEventProgressSubsystemCodec,
    EncounterMemorySubsystemCodec,
    SlidingWindowMemorySubsystemCodec,
    SpotExplorationProgressSubsystemCodec,
    SpotInteriorSubsystemCodec,
    WeatherSubsystemCodec,
    WorldFlagsSubsystemCodec,
    WorldTickSubsystemCodec,
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

EXPECTED_WORLD_SUBSYSTEM_KEYS: tuple[str, ...] = (
    # Phase 9-2
    "world_tick",
    "player_position",
    "player_vitals",
    "player_needs",
    # Phase 9-2b
    "player_inventory",
    "player_growth",
    "player_state_dict",
    # Phase 9-3
    "world_flags",
    "scenario_event_progress",
    "exploration_progress",
    # Phase 9-3b
    "spot_interior",
    "item_instance",
    # Phase 9-4a
    "player_active_effects",
    "player_attention_level",
    "player_pursuit_state",
    "player_spot_navigation_state",
    # Phase 9-4b
    "weather",
    "day_night",
    # Phase 9-4c
    "sliding_window",
    "observation_buffer",
    "action_result_store",
    # Encounter Memory
    "encounter_memory",
    # PR #752: save→restore 境界で当日分の腐敗通知を失わない
    "pending_food_spoilage",
)


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


def _empty_recall_slot_store() -> Any:
    """PR-G: snapshot 配線時に slot が未配線なら空 in-memory store で代用する。"""
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        InMemoryEpisodicRecallSlotStore,
    )

    return InMemoryEpisodicRecallSlotStore()


def _empty_afterglow_store() -> Any:
    """PR-G: snapshot 配線時に afterglow が未配線なら空 in-memory store で代用する。"""
    from ai_rpg_world.application.llm.services.afterglow_store import (
        InMemoryAfterglowStore,
    )

    return InMemoryAfterglowStore()


def _empty_recall_habituation_store() -> Any:
    """PR-G: snapshot 配線時に habituation が未配線なら空 in-memory store で代用する。"""
    from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
        InMemoryEpisodicRecallHabituationStore,
    )

    return InMemoryEpisodicRecallHabituationStore()


def _empty_belief_evidence_buffer_store() -> Any:
    """U2 (証拠台帳統一設計): snapshot 配線時に belief evidence buffer が
    未配線 (= flag OFF) なら空 in-memory store で代用する。"""
    from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
        InMemoryBeliefEvidenceBufferStore,
    )

    return InMemoryBeliefEvidenceBufferStore()


def _empty_recall_success_store() -> Any:
    """U9b (予測誤差統一設計 部品5・想起の信用割り当て): snapshot 配線時に

    的中側 sidecar が未配線 (= flag OFF) なら空 in-memory store で代用する。"""
    from ai_rpg_world.application.llm.services.episodic_recall_success_store import (
        InMemoryEpisodicRecallSuccessStore,
    )

    return InMemoryEpisodicRecallSuccessStore()


def _empty_pending_prediction_store() -> Any:
    """U10a (予測誤差統一設計 部品6・pending prediction): snapshot 配線時に

    pending prediction store が未配線 (= flag OFF) なら空 in-memory store で
    代用する (checklist #27)。"""
    from ai_rpg_world.application.llm.services.in_memory_pending_prediction_store import (
        InMemoryPendingPredictionStore,
    )

    return InMemoryPendingPredictionStore()


def _empty_goal_journal_store() -> Any:
    """P5 (目的層): snapshot 配線時に goal store が未配線 (= flag OFF) なら

    空 in-memory store で代用する (checklist #27)。"""
    from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
        InMemoryGoalJournalStore,
    )

    return InMemoryGoalJournalStore()


def _empty_stagnation_pressure_store() -> Any:
    """P-U2 (停滞感 store): snapshot 配線時に停滞感 store が未配線 (= flag OFF)

    なら空 in-memory store で代用する (checklist #27)。"""
    from ai_rpg_world.application.llm.services.in_memory_stagnation_pressure_store import (
        InMemoryStagnationPressureStore,
    )

    return InMemoryStagnationPressureStore()


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
    # Phase 7 (Issue #470): 各 snapshot ファイルから読み取った metadata。
    # ``source_scenario`` が現 scenario と異なる場合は別シナリオへの
    # cross-transfer (= わざと許容、warning ログのみ)。
    metadata_by_being: dict[BeingId, BeingSnapshotFileMetadata | None] = field(
        default_factory=dict
    )
    cross_scenario_transfers: list[tuple[BeingId, str, str]] = field(
        default_factory=list
    )  # (being_id, source_scenario, current_scenario)


def _default_world_subsystem_codecs() -> list[WorldSubsystemCodec]:
    """Phase 9-2/9-2b 既定で登録する subsystem codec 一覧。

    順序は **capture / restore の順番** に影響する。restore 時に依存関係が
    ある場合に意味を持つ。現状の codec 群は相互依存なし。
    growth は base_stats を内含するので vitals (= max_hp 由来) より先に
    restore したいが、本 PR の vitals codec は ``hp_max`` を直接保存して
    いるので順序非依存。
    """
    return [
        # Phase 9-2
        WorldTickSubsystemCodec(),
        PlayerPositionSubsystemCodec(),
        PlayerVitalsSubsystemCodec(),
        PlayerNeedsSubsystemCodec(),
        # Phase 9-2b
        PlayerInventorySubsystemCodec(),
        PlayerGrowthSubsystemCodec(),
        PlayerStateDictSubsystemCodec(),
        # Phase 9-3 (world-side flags / progress)
        WorldFlagsSubsystemCodec(),
        ScenarioEventProgressSubsystemCodec(),
        SpotExplorationProgressSubsystemCodec(),
        # Phase 9-3b (spot interior + item instance dynamic state)
        SpotInteriorSubsystemCodec(),
        ItemInstanceSubsystemCodec(),
        # Phase 9-4a (PlayerStatusAggregate combat/navigation sub-state)
        PlayerActiveEffectsSubsystemCodec(),
        PlayerAttentionLevelSubsystemCodec(),
        PlayerPursuitStateSubsystemCodec(),
        PlayerSpotNavigationStateSubsystemCodec(),
        # Phase 9-4b (world-side time/weather; day_night は tick 復元後に再計算)
        WeatherSubsystemCodec(),
        DayNightSubsystemCodec(),
        # Phase 9-4c (短期記憶 = LLM agent の prompt context)
        SlidingWindowMemorySubsystemCodec(),
        ObservationBufferSubsystemCodec(),
        ActionResultStoreSubsystemCodec(),
        # Encounter Memory (PR3 で runtime._encounter_memory を wiring 完了)。
        # familiarity 信号 (初対面 / 再会 / 初訪問 / 再訪) を永続化する。
        EncounterMemorySubsystemCodec(),
        # 再開保証: 日次 flush 前の未通知腐敗バッファ。
        # capture 前に flush すると連続 run と resume run で観測時刻がズレるため、
        # バッファ自体を保存して既存 day boundary flush に任せる。
        PendingFoodSpoilageSubsystemCodec(),
    ]


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

        # 任意 store: 「未配線なら空 in-memory store で代用」する。world_runtime
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
        # PR-G: 想起階層 (slot / afterglow / habituation) は wiring_result が
        # 露出していないことが多い (= episodic_stack が enable のときだけ wire
        # される) ので、未配線なら空 in-memory store にフォールバックする。
        recall_slot_store = (
            getattr(wiring_result, "recall_slot_store", None)
            or _empty_recall_slot_store()
        )
        afterglow_store = (
            getattr(wiring_result, "afterglow_store", None)
            or _empty_afterglow_store()
        )
        recall_habituation_store = (
            getattr(wiring_result, "recall_habituation_store", None)
            or _empty_recall_habituation_store()
        )
        # U2 (証拠台帳統一設計): belief evidence buffer も未配線なら空
        # in-memory store にフォールバックする (= flag OFF の run でも
        # snapshot 自体は壊れず「空の payload」で整合性が保たれる)。
        belief_evidence_buffer_store = (
            getattr(wiring_result, "belief_evidence_buffer_store", None)
            or _empty_belief_evidence_buffer_store()
        )
        # U9b (予測誤差統一設計 部品5・想起の信用割り当て): 的中側 sidecar も
        # 未配線なら空 in-memory store にフォールバックする (checklist #27)。
        recall_success_store = (
            getattr(wiring_result, "recall_success_store", None)
            or _empty_recall_success_store()
        )
        # U10a (予測誤差統一設計 部品6・pending prediction): pending prediction
        # store も未配線なら空 in-memory store にフォールバックする
        # (checklist #27)。
        pending_prediction_store = (
            getattr(wiring_result, "pending_prediction_store", None)
            or _empty_pending_prediction_store()
        )
        # P5 (目的層): goal store も未配線なら空 in-memory store にフォール
        # バックする (checklist #27)。
        goal_journal_store = (
            getattr(wiring_result, "goal_journal_store", None)
            or _empty_goal_journal_store()
        )
        # P-U2 (停滞感 store): 停滞感 store も未配線なら空 in-memory store に
        # フォールバックする (checklist #27)。
        stagnation_pressure_store = (
            getattr(wiring_result, "stagnation_pressure_store", None)
            or _empty_stagnation_pressure_store()
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
                # PR-G: 想起階層 3 store も fallback 監視対象に入れる。配線漏れで
                # 空 store にフォールバックしたことを後追いできるようにする。
                "recall_slot_store",
                "afterglow_store",
                "recall_habituation_store",
                # U2: belief evidence buffer も同じ監視対象に入れる。
                "belief_evidence_buffer_store",
                # U9b: 的中側 sidecar も同じ監視対象に入れる。
                "recall_success_store",
                # U10a: pending prediction store も同じ監視対象に入れる。
                "pending_prediction_store",
                # P5: goal store も同じ監視対象に入れる。
                "goal_journal_store",
                # P-U2: 停滞感 store も同じ監視対象に入れる。
                "stagnation_pressure_store",
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
            recall_slot_store=recall_slot_store,
            afterglow_store=afterglow_store,
            recall_habituation_store=recall_habituation_store,
            belief_evidence_buffer_store=belief_evidence_buffer_store,
            recall_success_store=recall_success_store,
            pending_prediction_store=pending_prediction_store,
            goal_journal_store=goal_journal_store,
            stagnation_pressure_store=stagnation_pressure_store,
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
        # Phase 9-2: 既定で 4 つの subsystem codec を登録する
        # (= tick / position / vitals / needs)。Tier 1a の核となる
        # 部分を resume できる。inventory / 残り status は Phase 9-2b 以降。
        # ``override_codecs`` を将来追加するなら ``__init__`` に kwarg を
        # 増やしてここを差し替えるパターン。
        self._world_snapshot_service = WorldStateSnapshotService(
            subsystem_codecs=_default_world_subsystem_codecs(),
            expected_subsystem_keys=EXPECTED_WORLD_SUBSYSTEM_KEYS,
        )
        self._world_gateway = WorldStateSnapshotFileGateway()

    @property
    def snapshot_dir(self) -> Path:
        return self._snapshot_dir

    # ---- Phase 9-1: world snapshot ----------------------------------------
    def capture_world(
        self,
        runtime: Any,
        *,
        source_scenario: str,
        world_tick: int,
    ) -> Path:
        """world snapshot を取って ``snapshot_dir/world.json`` に書く。

        Phase 9-1: 中身の subsystem は未登録なので ``subsystems={}`` の空
        snapshot が出る。Phase 9-2 以降で 1 subsystem ずつ追加される。
        失敗時は例外伝播 (= warning でなく hard 失敗 = world は中途半端
        だと意味がない)。
        """
        from datetime import datetime, timezone

        snapshot = self._world_snapshot_service.capture(
            runtime,
            source_scenario=source_scenario,
            world_tick=world_tick,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )
        return self._world_gateway.write(snapshot, self._snapshot_dir)

    def restore_world_from_dir(
        self,
        runtime: Any,
        input_dir: Path,
        *,
        current_scenario: str,
    ) -> WorldStateSnapshot | None:
        """``input_dir/world.json`` を読み runtime に書き戻す。

        ``world.json`` が無ければ ``None`` を返す (= 旧 snapshot directory
        (Being snapshot のみ) との後方互換)。あれば fail-fast で復元する。
        scenario 不一致は ``WorldStateScenarioMismatchError`` で停止
        (= world は scenario 依存なので別 scenario への load は不可)。
        """
        if not self._world_gateway.exists_in(input_dir):
            logger.info(
                "no world.json in %s; skipping world state restore "
                "(legacy snapshot directory)",
                input_dir,
            )
            return None
        snapshot = self._world_gateway.read(input_dir)
        self._world_snapshot_service.restore(
            runtime,
            snapshot,
            current_scenario=current_scenario,
            strict_subsystems=True,
        )
        return snapshot

    @property
    def world_snapshot_service(self) -> WorldStateSnapshotService:
        """world snapshot service への公開アクセサ (= test / Phase 9-2 以降の
        subsystem 登録用)。"""
        return self._world_snapshot_service

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
        self,
        player_ids: Sequence[PlayerId],
        *,
        source_scenario: str | None = None,
    ) -> CaptureAllReport:
        """全 player の Being snapshot を ``snapshot_dir`` 配下に書き出す。

        各 player の失敗は warning に残しつつ続行 (= 全体が止まらない)。
        実験 run のデータ救済を最優先する設計。

        Phase 7: ``source_scenario`` を渡すと snapshot file の ``_metadata``
        に埋め込まれ、後で ``restore_all_from_dir`` 経由で読めば
        cross-scenario transfer を検知できる。
        """
        self._snapshot_dir.mkdir(parents=True, exist_ok=True)
        mappings = self._resolve_player_being_ids(player_ids)
        succeeded: list[BeingId] = []
        failed: list[tuple[BeingId, str]] = []
        # captured_at は呼出側 (= runner) で 1 度生成して渡したい場合もあるが、
        # 現状は session 内で 1 度だけ取って全 player に揃える (= run 終了時の
        # 1 snapshot run = 同タイムスタンプ)。
        from datetime import datetime, timezone

        captured_at = datetime.now(timezone.utc).isoformat()
        metadata = BeingSnapshotFileMetadata(
            source_scenario=source_scenario,
            captured_at=captured_at,
        )
        for m in mappings:
            try:
                self._capture_use_case.execute(
                    m.being_id, m.file_path, metadata=metadata
                )
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
            except SnapshotCoverageError:
                # PR-F: 「新 store を追加して capture() を更新し忘れた」状態
                # を表す programming error。実験 run を続行させると 全 Being の
                # snapshot が壊れたまま完走してしまう (= 起動時 fail-fast の
                # 意図を裏切る) ので、warning に丸めずそのまま伝播させる。
                raise
            except Exception as exc:  # noqa: BLE001 - 実験 run の生命を最優先
                logger.warning(
                    "snapshot capture failed for being_id=%s: %s",
                    m.being_id.value,
                    exc,
                    exc_info=True,
                )
                failed.append((m.being_id, repr(exc)))
        return CaptureAllReport(succeeded=succeeded, failed=failed)

    def restore_all_from_dir(
        self,
        input_dir: Path,
        *,
        current_scenario: str | None = None,
    ) -> RestoreAllReport:
        """``input_dir`` 配下の ``*.json`` を全て restore する。

        1 件でも失敗したら例外 (= partial state で experiment を始めない
        fail-fast)。ファイルがゼロ件なら no-op で空 report を返す。

        Phase 7: ``current_scenario`` を渡すと、各 snapshot の
        ``_metadata.source_scenario`` と比較し、異なれば
        ``cross_scenario_transfers`` に記録 + warning ログを出す。
        **mismatch はエラーにしない** (= 同じキャラクターを別シナリオに
        転送する use case を許容)。
        """
        if not input_dir.exists():
            raise FileNotFoundError(
                f"snapshot dir does not exist: {input_dir}"
            )
        if not input_dir.is_dir():
            raise NotADirectoryError(f"not a directory: {input_dir}")

        # ファイル名順で読み込む = 決定的な順序にする (= 復元が冪等)。
        # Phase 9-1: ``world.json`` は別 path (= WorldStateSnapshot) なので
        # Being restore のループからは除外する。
        files = sorted(
            p
            for p in input_dir.iterdir()
            if p.suffix == ".json" and p.name != "world.json"
        )
        restored: list[BeingId] = []
        metadata_by_being: dict[BeingId, BeingSnapshotFileMetadata | None] = {}
        cross_transfers: list[tuple[BeingId, str, str]] = []
        for path in files:
            # metadata は restore_use_case の中では読まないので、別途 gateway
            # から読む (= 失敗しても restore 本体は続行 = silent failure 防止
            # のため warning ログのみ)。
            try:
                metadata = self._gateway.read_metadata(path)
            except Exception:
                logger.warning(
                    "failed to read metadata from %s; continuing without metadata",
                    path,
                    exc_info=True,
                )
                metadata = None

            result = self._restore_use_case.execute(path)
            restored.append(result.being_id)
            metadata_by_being[result.being_id] = metadata
            logger.info(
                "snapshot restored: being_id=%s file=%s memory_restored=%s",
                result.being_id.value,
                path,
                result.memory_restored,
            )

            # cross-scenario 検知。両方とも None でない時だけ比較。
            if (
                metadata is not None
                and metadata.source_scenario is not None
                and current_scenario is not None
                and metadata.source_scenario != current_scenario
            ):
                cross_transfers.append(
                    (
                        result.being_id,
                        metadata.source_scenario,
                        current_scenario,
                    )
                )
                logger.warning(
                    "cross-scenario transfer detected: being_id=%s "
                    "saved in scenario %r, loading into scenario %r "
                    "(allowed but flagged)",
                    result.being_id.value,
                    metadata.source_scenario,
                    current_scenario,
                )
        return RestoreAllReport(
            restored=restored,
            metadata_by_being=metadata_by_being,
            cross_scenario_transfers=cross_transfers,
        )


__all__ = [
    "ExperimentSnapshotSession",
    "CaptureAllReport",
    "EXPECTED_WORLD_SUBSYSTEM_KEYS",
    "RestoreAllReport",
]
