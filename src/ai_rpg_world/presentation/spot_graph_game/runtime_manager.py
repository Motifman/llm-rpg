"""Central manager that bridges FastAPI routers with the game runtime.

Wires ``EscapeGameRuntime`` / scenario loaders / session lifecycle to
the API layer.  Methods that are not yet backed by real logic return
stub data so that the full API surface remains exercisable.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator, Iterable
from dataclasses import dataclass, field, replace as dataclass_replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.interfaces import ILLMPlayerResolver
from ai_rpg_world.application.intent.action_failed_observation_emitter import (
    ActionFailedObservationEmitter,
)
from ai_rpg_world.application.intent.intent_id_generator import (
    IntentIdGenerator,
)
from ai_rpg_world.application.intent.tool_phase_mapping import phase_for_tool
from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    ToolRuntimeTargetDto,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)
from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_env,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.intent.value_object.intent import Intent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMappingError
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
from ai_rpg_world.presentation.spot_graph_game.schemas import (
    CharacterCreateRequest,
    CharacterDetailResponse,
    CharacterInSpotResponse,
    CharacterSummaryResponse,
    CharacterUpdateRequest,
    ChatHistoryResponse,
    ChatMessageResponse,
    ChatSendRequest,
    EventLogResponse,
    InventoryItemResponse,
    InventoryResponse,
    ResultImpressionResponse,
    ResultRelationshipResponse,
    ResultTimelineResponse,
    SaveListResponse,
    SaveSlotResponse,
    SessionCreateRequest,
    SessionStateResponse,
    SessionSummaryResponse,
    SpotConnectionResponse,
    SpotObjectResponse,
    SpotViewResponse,
    WorldDetailResponse,
    WorldSummaryResponse,
)

logger = logging.getLogger(__name__)


def _character_to_escape_prompt_input(
    character: Optional[CharacterDetailResponse],
) -> Optional[EscapeCharacterPromptInput]:
    if character is None:
        return None
    return EscapeCharacterPromptInput(
        character_id=character.id,
        name=character.name,
        first_person=character.first_person or "私",
        personality_tags=tuple(character.personality_tags or ()),
        appearance=character.appearance or "",
        speech_samples=tuple(character.speech_samples or ()),
        fragmented_memory=character.fragmented_memory or "",
        values=character.values or "",
        strengths=character.strengths or "",
        weaknesses=character.weaknesses or "",
        interpersonal_tendency=character.interpersonal_tendency or "",
        behavioral_rules=tuple(character.behavioral_rules or ()),
    )


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class _EscapeSpawnAllPlayersLlmResolver(ILLMPlayerResolver):
    """スポーンした全員をプレゼン層脱出セッションでは LLM ターン対象とみなす。"""

    spawn_player_ids: frozenset[int]

    def is_llm_controlled(self, player_id: PlayerId) -> bool:
        return player_id.value in self.spawn_player_ids


# ──────────────────────────────────────────────────────────────────
# 失敗 message learnable 化ヘルパーは ``application/llm/services/
# failure_helpers.py`` に集約済 (Issue #168 で executor 横断展開のため
# 共通モジュールへ昇格)。本ファイル内では既存呼び出し / テストの後方
# 互換のため private alias を再エクスポートする。
#
# 旧: ``runtime_manager._list_object_labels(targets)``
# 新: ``failure_helpers.list_object_labels(targets)`` と同じ実装が動く。
# ──────────────────────────────────────────────────────────────────

from ai_rpg_world.application.llm.services.failure_helpers import (  # noqa: E402
    list_destination_labels as _list_destination_labels,
    list_object_labels as _list_object_labels,
    list_player_labels as _list_player_labels,
    list_targets_of_kind as _list_targets_of_kind,
)


# N2: 「枯渇 / 同じ tick 内に再採取できない」系の失敗 reason を検知する
# キーワード集。マッチしたら「同じ object に同 action_name を retry しない」
# 旨の remediation に切り替える (= LLM が同じ枯渇 resource を回し続ける
# 無限 retry の抑制)。
_INTERACTION_EXHAUST_HINTS = (
    "採り尽く",
    "枯渇",
    "もう空",
    "もう開い",
    "すでに",
    "今は",
    "燃え上が",
)


def _interact_remediation_for_reason(reason: str) -> str:
    if any(k in reason for k in _INTERACTION_EXHAUST_HINTS):
        return (
            "同じ object に同 action_name を再試行しても結果は変わらない。"
            "別の場所・別 object・別 action を選ぶか、必要な前提アイテムを"
            "先に揃えてから戻ること。"
        )
    return (
        "前提条件 (必要アイテム / 体力 / 天候 / フラグ) を満たしてから再試行する。"
        "失敗 reason に名指しされたアイテムや状態を確認すること。"
    )


def _list_object_interactions(runtime: Any, object_id: Any) -> list[str]:
    """`object_id` が所属する spot の interior から available action 名を列挙。

    実験 #26 で LLM が "search" / "examine" 等の ad-hoc action_name を発明して
    InteractionNotFoundException が generic error に化けていた問題を直すため、
    handler が remediation で正規の action 一覧を返せるようにするヘルパ。
    解決経路で例外が出たら空 list を返す (= remediation 文面が "(なし)" になる)。
    """
    try:
        graph = runtime._spot_graph_repo.find_graph()
        spot_id = None
        # object_id (SpotObjectId) から所属 spot を探す
        for node in graph.iter_spot_nodes():
            interior = runtime._spot_interior_repo.find_by_spot_id(node.spot_id)
            if interior is None:
                continue
            obj = interior.get_object(object_id)
            if obj is not None:
                return [i.action_name for i in obj.interactions]
        return []
    except Exception:
        return []


def _safe_get_str(mapper: Any, namespace: str, numeric_id: int) -> str:
    """Return the string ID for *numeric_id*, falling back to str(numeric_id)."""
    try:
        return mapper.get_str(namespace, numeric_id)
    except (ScenarioIdMappingError, KeyError):
        return str(numeric_id)


def _read_scenario_metadata(path: Path) -> Optional[Dict[str, Any]]:
    """Read only the metadata section from a scenario JSON without full parse."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        return raw
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read scenario %s: %s", path, exc)
        return None


@dataclass
class _QueuedTurnTrigger:
    """Minimal turn scheduler used until the API runtime is wired to real LLM turns."""

    pending_player_ids: set[int] = field(default_factory=set)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.pending_player_ids.add(player_id.value)

    def run_scheduled_turns(self) -> None:
        self.pending_player_ids.clear()


# Step 1 並列化 (#346 ロードマップ): 1 tick 内の Phase A (= 各プレイヤーが
# 自分の snapshot を読んで LLM を叩く部分) を ThreadPoolExecutor で N 並列で
# 走らせ、Phase B (= tool 適用 / 世界 mutation) は to_run 順に serial で適用
# する。LLM 呼び出しがブロッキング HTTP な間に他プレイヤーの呼び出しが進む
# ので、4 人 × 2s ≈ 2s/tick に圧縮できる (シリアル時は 8s/tick)。
#
# env で workers を制御できる。0 / 未指定なら従来通り完全 serial。
_LLM_PARALLEL_WORKERS_ENV = "LLM_TURN_PARALLEL_WORKERS"


def _resolve_llm_parallel_workers(default: int = 0) -> int:
    """env から並列度を読む。0 以下 / 不正値ならシリアル動作 (= 0)。"""
    raw = os.environ.get(_LLM_PARALLEL_WORKERS_ENV)
    if raw is None:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    return max(0, n)


class _LlmMetricsTraceSink:
    """Phase A の LLM 呼び出し metrics を trace に流す sink (PR #358)。

    Review HIGH 2 対応: current_tick は ``record()`` 呼び出し時点で取得する
    (sink 構築時に固定すると、遅い LLM 呼び出しが tick 境界を跨いだ場合に
    stale tick で記録される。後の τ_sim 分析の信頼性に関わる)。

    Review MEDIUM 対応: 旧実装は inner class を毎呼び出し定義していたが、
    parallel hot path で無駄なので module-level に切り出した。
    """

    def __init__(
        self,
        trace_recorder: Any,
        runtime: Any,
        player_id: PlayerId,
    ) -> None:
        self._trace_recorder = trace_recorder
        self._runtime = runtime
        self._player_id_value = int(player_id.value)

    def record(self, metrics: Any) -> None:
        try:
            tick: Optional[int] = None
            try:
                tick = int(self._runtime.current_tick())
            except Exception:
                tick = None
            from ai_rpg_world.application.trace import TraceEventKind
            self._trace_recorder.record(
                TraceEventKind.LLM_CALL,
                tick=tick,
                player_id=self._player_id_value,
                model=metrics.model,
                wall_latency_ms=metrics.wall_latency_ms,
                prompt_tokens=metrics.prompt_tokens,
                completion_tokens=metrics.completion_tokens,
                cached_tokens=metrics.cached_tokens,
                tps=metrics.tps,
                success=metrics.success,
                error_code=metrics.error_code,
            )
            # #404 P2: progress.jsonl 用 LLM 呼び出しカウンタを bump。
            # runtime 側に counter が無いランタイム (presentation 単体テスト等)
            # は getattr で安全に skip する。
            bump = getattr(self._runtime, "bump_llm_call_count", None)
            if callable(bump):
                try:
                    bump()
                except Exception:
                    # counter 失敗は trace 記録自体を壊さない
                    pass
        except Exception:
            logger.exception("trace_recorder.record(llm_call) failed")


@dataclass
class _LlmPhaseAResult:
    """1 ターンの Phase A (snapshot + LLM 呼び出し) の出力。

    Phase B (tool 実行) の入力として保持する。LLM 呼び出し例外を捕まえた場合は
    ``exception`` に詰め、Phase B 側で LlmCommandResultDto を組み立てる。
    """
    player_id: PlayerId
    prompt: dict
    tools_payload: list
    tool_call: Optional[dict]
    exception: Optional[BaseException]


@dataclass
class _EscapeGameLlmTurnTrigger:
    """Queues escape-game LLM turns and runs them against the session runtime."""

    wiring: "_EscapeGameLlmWiring"
    max_turns: int = 5
    pending_player_ids: set[int] = field(default_factory=set)
    _turn_counts: dict[int, int] = field(default_factory=dict)

    def schedule_turn(self, player_id: PlayerId) -> None:
        self.pending_player_ids.add(player_id.value)
        # PR 7 (#227 review HIGH 2): カウントを 0 リセットせずに保持する。
        # 旧コードは schedule_turn のたびに `_turn_counts[pid] = 0` でリセット
        # していたため、PR 2 で speech が ObservationTurnScheduler 経由で再
        # スケジュールされるようになった後は、turn loop 中に他者発話が来ると
        # max_turns 制限が事実上無効化される (2 プレイヤー間で交互に発話が
        # 続くと無限ループの可能性)。setdefault で「未登録なら 0、既登録なら
        # 維持」に変更。
        self._turn_counts.setdefault(player_id.value, 0)

    def run_scheduled_turns(self) -> None:
        # #363 Fix 1a: ゲーム既終了なら一切 LLM を回さない。実験 #25 ON_FULL で
        # 全員 DEAD 後も LLM ターン継続 → 駆動 tick 107 が 49 分ハングした
        # silent failure を防ぐ。check_game_end() は all_resolved() で O(N)、
        # 毎 tick 叩いても問題ない軽さ。
        runtime = self.wiring.runtime
        check_game_end = getattr(runtime, "check_game_end", None)
        if callable(check_game_end):
            try:
                if check_game_end().is_ended:
                    self.pending_player_ids.clear()
                    self._turn_counts.clear()
                    return
            except Exception:
                # check_game_end 自体が落ちても turn 実行を続ける fail-safe
                logger.exception("check_game_end raised; continuing turn execution")

        to_run = list(self.pending_player_ids)
        self.pending_player_ids.clear()
        # #363 Fix 1b: 行動不可 (is_down / outcome 確定) のプレイヤーを除外。
        # 死亡したプレイヤーが speech 観測などで起こされるケースがあるため、
        # to_run の filter は確実に必要。
        to_run = [pid for pid in to_run if self._can_player_act(pid)]
        if not to_run:
            return

        workers = _resolve_llm_parallel_workers()
        if workers <= 1 or len(to_run) <= 1:
            # 旧シリアル経路: 並列化を OFF にした / プレイヤーが 1 人だけ。
            # 完全に従来挙動。
            for player_id_value in to_run:
                result = self.wiring.run_turn(PlayerId(player_id_value))
                self._account_result(player_id_value, result)
            return

        # 並列 Phase A: 各プレイヤーの prompt 構築 + LLM 呼び出しを ThreadPool
        # で同時実行する。litellm.completion はブロッキング HTTP なので、
        # CPython の GIL を解放して並列に走る。
        # 制約: build_full_prompt は observation buffer を drain するが、
        # buffer は player_id keyed の dict なので別プレイヤー間で衝突しない。
        max_workers = min(workers, len(to_run))
        phase_a_results: dict[int, _LlmPhaseAResult] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(
                    self.wiring.run_phase_a, PlayerId(pid_value)
                ): pid_value
                for pid_value in to_run
            }
            for future in futures:
                pid_value = futures[future]
                # 例外は Phase A 内で捕まえて _LlmPhaseAResult.exception に
                # 詰めてあるので、future.result() がさらに raise することは
                # 基本ない (Defense-in-depth で try/except)。
                try:
                    phase_a_results[pid_value] = future.result()
                except Exception as exc:
                    logger.exception(
                        "Phase A failed for player_id=%s", pid_value
                    )
                    phase_a_results[pid_value] = _LlmPhaseAResult(
                        player_id=PlayerId(pid_value),
                        prompt={},
                        tools_payload=[],
                        tool_call=None,
                        exception=exc,
                    )

        # Phase B は serial: to_run 順に世界 mutation を適用する。
        # 観測 broadcast / trace recording の順序も to_run 順で確定する。
        for pid_value in to_run:
            phase_a = phase_a_results.get(pid_value)
            if phase_a is None:
                continue
            result = self.wiring.run_phase_b(phase_a)
            self._account_result(pid_value, result)

    def _account_result(
        self, player_id_value: int, result: LlmCommandResultDto
    ) -> None:
        """ターン後の reschedule / turn count 管理を 1 か所に集約する。"""
        current_count = self._turn_counts.get(player_id_value, 0) + 1
        if result.was_no_op:
            self._turn_counts.pop(player_id_value, None)
        elif result.should_reschedule or current_count < self.max_turns:
            self.pending_player_ids.add(player_id_value)
            self._turn_counts[player_id_value] = current_count
        else:
            self._turn_counts.pop(player_id_value, None)

    def _can_player_act(self, player_id_value: int) -> bool:
        """#363 Fix 1b: 行動不可なプレイヤーを LLM 経路から除外する。

        判定:
        - outcome 確定 (DEAD / STRANDED / RESCUED) → 行動不可
        - is_down (= can_act() False) → 行動不可
        - 上記いずれも当たらない / 情報不足 → 行動可 (fail-safe で turn を回す)

        実験 #25 ON_FULL では死亡後も speech 観測等で起こされて LLM ターン
        が継続し、駆動 tick が膨張した。filter を入れて死亡 player を skip。
        """
        runtime = self.wiring.runtime
        # 1. outcome registry を見る (最も明確なシグナル)
        outcome_registry = getattr(runtime, "_player_outcome_registry", None)
        if outcome_registry is not None:
            try:
                outcome = outcome_registry.get_outcome(PlayerId(player_id_value))
                if outcome.is_resolved:
                    return False
            except Exception:
                # registry エラーは fail-safe で turn 継続。ただし silent failure
                # にすると registry 自体の異常 (永続化先の dead lock 等) を
                # 永遠に検知できないため、warning でログを残す。
                logger.warning(
                    "outcome_registry.get_outcome failed for player_id=%s; "
                    "falling back to turn-continue", player_id_value,
                    exc_info=True,
                )
        # 2. status.can_act() を見る (is_down 等の遷移を含む)
        status_repo = getattr(runtime, "_player_status_repo", None)
        if status_repo is None:
            return True
        try:
            status = status_repo.find_by_id(PlayerId(player_id_value))
            if status is None:
                return True
            if not status.can_act():
                return False
            # #404 fix: 移動中 (is_traveling=True) の player は LLM ターンを
            # 回さない。意味論として「移動中は次の意思決定をしない」が自然で、
            # かつ heartbeat / observation で起こされても turn 実行を空回り
            # させない。到着時に SpotGraphTravelStageService.on_arrival
            # 経由で schedule_turn が打たれて再開する。
            nav = status.spot_navigation_state
            if nav is not None and nav.is_traveling:
                return False
            return True
        except Exception:
            logger.warning(
                "player_status_repo.find_by_id failed for player_id=%s; "
                "falling back to turn-continue", player_id_value,
                exc_info=True,
            )
            return True


@dataclass
class _EscapeGameLlmWiring:
    """Session-local LLM loop for the escape-game runtime.

    **Two-phase construction invariant**:
    ``action_failed_emitter`` と ``intent_id_generator`` は ``ObservationTurnScheduler``
    → ``ActionFailedObservationEmitter`` の構築連鎖が ``llm_turn_trigger`` を
    必要とするため、本クラスの ``__init__`` 直後に注入する必要がある。
    ``create_session`` の流れは:

        1. ``_EscapeGameLlmWiring(...)`` を ctor で作成 (内部で trigger 生成)
        2. ``ObservationTurnScheduler`` を trigger を使って組み立て
        3. ``ActionFailedObservationEmitter`` を scheduler を使って組み立て
        4. ``attach_action_failed_wiring(emitter, generator)`` を呼ぶ
        5. ``self._sessions[sid]`` に登録 (これ以降 tick loop から見える)

    手順 4 を踏まずに 5 に到達すると、失敗 DTO が出ても観測化されない silent
    bug になる。アサーションで防げないため (Optional として動かす設計)、本
    docstring の手順を守ること。
    """

    runtime: Any
    observation_buffer: Any
    llm_client: Any = field(default_factory=create_llm_client_from_env)
    max_turns: int = 5
    # 失敗 DTO を ActionFailed 観測に変換する emitter (Optional)。
    # ``attach_action_failed_wiring`` で配線される。None の場合は失敗観測を
    # 発行しない (後方互換 / テスト用ショートカット)。
    action_failed_emitter: Optional[ActionFailedObservationEmitter] = None
    # ActionFailed 観測の intent.intent_id を払い出すカウンタ。
    # action_failed_emitter とセットで使う想定。
    intent_id_generator: Optional[IntentIdGenerator] = None

    def __post_init__(self) -> None:
        self.observation_appender = ObservationAppender(self.observation_buffer)
        self.llm_turn_trigger = _EscapeGameLlmTurnTrigger(
            wiring=self,
            max_turns=self.max_turns,
        )
        # PR 4 (#227): 同一ツール連打を engine 側で検知し、警告を観測として
        # 注入する loop guard。PR #230 で LlmAgentOrchestrator 経由で配線
        # していたが、escape_game の独自 turn 実行はそれを経由しないため、
        # ここで wiring に直接組み込む。閾値は ToolCallLoopGuardService の
        # 既定値 (wait=3 / travel_to=2 / interact=4 / その他=5) を使う。
        # Issue #240 後続: trace_recorder + current_tick_provider を注入し、
        # loop_guard 警告が trace.jsonl に LOOP_GUARD_WARNING として残るようにする。
        # 第15回実験で「警告は出てるはずなのに trace に痕跡なし」状態だったため。
        #
        # 注: runtime.trace_recorder は session 作成後に set_trace_recorder() で
        # 後から差し込まれるケース (実験スクリプト経路) があるため、
        # callable provider 経由で use 時に look-up する。
        self.tool_call_loop_guard = ToolCallLoopGuardService(
            observation_buffer=self.observation_buffer,
            trace_recorder_provider=lambda: getattr(
                self.runtime, "trace_recorder", None
            ),
            current_tick_provider=(
                self.runtime.current_tick
                if hasattr(self.runtime, "current_tick")
                else None
            ),
        )
        # PR 5 (#227): memo 完了 hint。LLM が memo_done を呼ばずに memo を
        # 放置するケースを救済するため、action_summary / result_summary と
        # 未完了 memo の content を SequenceMatcher で比較し、類似度が高ければ
        # 「memo を完了したかも」hint を result.message に append する。
        # PR #230 で本家経路に配線済みだが、escape_game の独自 turn 実行は
        # 経由しないため、ここで wiring に直接組み込む。
        memo_store = getattr(self.runtime, "_todo_store", None)
        self.memo_completion_hint_service: Optional[MemoCompletionHintService] = (
            MemoCompletionHintService(memo_store=memo_store)
            if memo_store is not None
            else None
        )
        # Issue #264 後続 B1: speech_say の audience resolver。
        # runtime の spot_graph_repo / player_status_repo / SoundPropagationService を
        # 集めて事前 audience 問い合わせを可能にする。これにより speech 結果
        # message に「届いた人数」を含められ、agent が空振りを学習できる。
        from ai_rpg_world.application.speech.services.speech_audience_resolver import (
            SpeechAudienceResolver,
        )
        from ai_rpg_world.domain.world_graph.service.sound_propagation_service import (
            SoundPropagationService,
        )
        spot_graph_repo = getattr(self.runtime, "_spot_graph_repo", None)
        player_status_repo = getattr(self.runtime, "_player_status_repo", None)
        self.speech_audience_resolver: Optional[SpeechAudienceResolver] = None
        if spot_graph_repo is not None and player_status_repo is not None:
            self.speech_audience_resolver = SpeechAudienceResolver(
                spot_graph_repository=spot_graph_repo,
                player_status_repository=player_status_repo,
                sound_propagation_service=SoundPropagationService(),
            )
        # PR 7 (#227): ツール名→ハンドラの dispatch table。本家
        # ToolCommandMapper.execute と構造を揃え、巨大 if-elif を排除する。
        # 各ハンドラは (player_id, arguments, runtime_context) を受けて
        # LlmCommandResultDto を返す。
        self._tool_handlers: Dict[
            str,
            Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto],
        ] = {
            TOOL_NAME_SPOT_GRAPH_EXPLORE: self._handle_explore,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO: self._handle_travel_to,
            TOOL_NAME_SPOT_GRAPH_INTERACT: self._handle_interact,
            TOOL_NAME_SPOT_GRAPH_LISTEN: self._handle_listen,
            TOOL_NAME_SPOT_GRAPH_WAIT: self._handle_wait,
            TOOL_NAME_SPEECH: self._handle_speech,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: self._handle_set_sub_location,
            TOOL_NAME_TODO_ADD: self._make_auxiliary_tool_handler(TOOL_NAME_TODO_ADD),
            TOOL_NAME_TODO_LIST: self._make_auxiliary_tool_handler(TOOL_NAME_TODO_LIST),
            TOOL_NAME_TODO_COMPLETE: self._make_auxiliary_tool_handler(
                TOOL_NAME_TODO_COMPLETE
            ),
        }
        # #344 配線漏れ修正: spot_graph_use_item / attack / give_item /
        # pickup_item / drop_item / prepare_action は application 層 (executor)
        # に実装があるが、experiment runtime の _tool_handlers に dispatch が
        # 無く UNSUPPORTED_TOOL に化けていた。executor を遅延構築し、これら
        # の handler を _tool_handlers に追加する。
        self._spot_graph_executor: Optional[Any] = None
        self._wire_missing_spot_graph_tools()

    def _wire_missing_spot_graph_tools(self) -> None:
        """#344: spot_graph_use_item / attack / give_item / pickup_item /
        drop_item / prepare_action を experiment runtime から呼べるよう、
        SpotGraphToolExecutor を runtime のリポジトリ群で組み立てて handler を
        merge する。

        runtime に必要なリポジトリ / orchestrator が揃っていない (= テストや
        minimal wiring) 場合は silent に skip する (該当ツールは旧来通り
        UNSUPPORTED_TOOL のままになるが、本来の experiment 経路では届く前提)。
        """
        runtime = self.runtime
        # 必須リポジトリ群。どれかが欠けたら executor の構築は諦める。
        needed = (
            "_player_inventory_repo",
            "_item_repo",
            "_player_status_repo",
            "_item_transfer_service",
            "_interaction_service",
            "_movement_service",
            "_exploration_service",
            "_world_flag_state",
            "_exploration_progress",
        )
        for attr in needed:
            if not hasattr(runtime, attr) or getattr(runtime, attr) is None:
                logger.warning(
                    "_wire_missing_spot_graph_tools: runtime is missing %s; "
                    "use_item / attack / give_item / pickup_item / drop_item / "
                    "prepare_action will remain UNSUPPORTED_TOOL.",
                    attr,
                )
                return

        from ai_rpg_world.application.world_graph.spot_graph_world_services import (
            SpotGraphWorldServices,
        )
        from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
            SpotGraphToolExecutor,
        )
        from ai_rpg_world.application.llm.tool_constants import (
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
        )
        from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
            GameEndConditionEvaluator,
        )

        services = SpotGraphWorldServices(
            interaction=runtime._interaction_service,
            exploration=runtime._exploration_service,
            world_flags=runtime._world_flag_state,
            game_end_evaluator=GameEndConditionEvaluator(),
            exploration_progress=runtime._exploration_progress,
            movement=runtime._movement_service,
        )
        # monster_repository / attack_orchestrator は monster placements を
        # 持つシナリオのみ runtime に存在する。spot_graph_attack は両方無いと
        # 「未対応」を返すよう executor 側で実装済み。
        # ConsumableUsedEvent を ConsumableEffectHandler に届けるため
        # pipeline_event_publisher を渡す。これがないと use_item が
        # 「使用した」success を返しつつ HP / hunger が変化しない silent
        # failure になる (#344 の隠れた半分)。
        event_publisher = getattr(runtime, "_speech_event_publisher", None)
        executor = SpotGraphToolExecutor(
            spot_graph_world_services=services,
            player_inventory_repository=runtime._player_inventory_repo,
            item_repository=runtime._item_repo,
            event_publisher=event_publisher,
            spot_graph_repository=runtime._spot_graph_repo,
            monster_repository=getattr(runtime, "_monster_repo", None),
            player_status_repository=runtime._player_status_repo,
            attack_orchestrator=getattr(runtime, "_attack_orchestrator", None),
            item_transfer_service=runtime._item_transfer_service,
            time_provider=getattr(runtime, "_time_provider", None),
        )
        self._spot_graph_executor = executor
        raw_handlers = executor.get_handlers()
        # executor は (player_id_int, args) -> result の signature。
        # _tool_handlers は (PlayerId, args, runtime_context) -> result なので
        # ラップして adapt する。runtime_context は executor 側で使わない。
        targets = (
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
        )
        # #356 実験 #25 OFF で発覚: use_item / drop_item / give_item /
        # pickup_item は tool catalog 上 ``item_label`` (= I1, I2 など) を
        # 受け取るが、executor は post-resolver の ``item_spec_id`` /
        # ``slot_id`` / ``item_instance_id`` を読む。それらの間を埋める
        # ``SpotGraphArgumentResolver`` の呼び出しが experiment 用 wiring
        # に無く、164 件すべて INVALID_ARGUMENT で落ちていた。
        # 解決後 args を executor に渡すように adapter で resolver を噛ませる。
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            SpotGraphArgumentResolver,
        )
        resolver_targets = frozenset({
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
        })
        argument_resolver = SpotGraphArgumentResolver()
        for tool_name in targets:
            raw = raw_handlers.get(tool_name)
            if raw is None:
                continue
            if tool_name in resolver_targets:
                self._tool_handlers[tool_name] = (
                    self._adapt_executor_handler_with_resolver(
                        raw, tool_name, argument_resolver,
                    )
                )
            else:
                self._tool_handlers[tool_name] = self._adapt_executor_handler(raw)
        # Step 1 並列化 review HIGH 1: build_full_prompt が内部で lazy-init する
        # _todo_tool_executor / _cached_default_prompt_builder は check-then-act
        # で 2 スレッドが同時に初回呼び出しすると double-init になる。並列実行
        # の前に単一スレッドで pre-warm して race を構造的に消す。
        try:
            if hasattr(runtime, "_wire_auxiliary_tool_stack"):
                runtime._wire_auxiliary_tool_stack()
            if hasattr(runtime, "_get_or_build_default_prompt_builder"):
                runtime._get_or_build_default_prompt_builder()
        except Exception:
            # pre-warm に失敗しても通常パスはあくまで lazy で動く。安全側 fallback。
            logger.exception(
                "Pre-warming auxiliary tool stack / default prompt builder failed; "
                "lazy initialization will fall back, but Phase A 並列化時に race の "
                "可能性が残る"
            )

    @staticmethod
    def _adapt_executor_handler(
        raw_handler: Callable[[int, Dict[str, Any]], LlmCommandResultDto],
    ) -> Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]:
        """executor signature (int, args) → wiring signature (PlayerId, args, ctx)。"""
        def _handler(
            player_id: PlayerId,
            arguments: Dict[str, Any],
            runtime_context: Any,
        ) -> LlmCommandResultDto:
            return raw_handler(int(player_id.value), arguments)
        return _handler

    @staticmethod
    def _adapt_executor_handler_with_resolver(
        raw_handler: Callable[[int, Dict[str, Any]], LlmCommandResultDto],
        tool_name: str,
        argument_resolver: Any,
    ) -> Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]:
        """resolver を噛ませた adapter (#356 fix)。

        LLM が送ってくる ``item_label`` (I1/I2) を、executor が読む
        ``item_spec_id`` / ``slot_id`` / ``item_instance_id`` に変換する。
        resolver が例外 (label 見つからない 等) を投げたら ``LlmCommandResultDto``
        に変換して返す (= LLM に「このラベルは存在しない」と surface する)。
        """
        from ai_rpg_world.application.llm.services._resolver_helpers import (
            ToolArgumentResolutionException,
        )

        def _handler(
            player_id: PlayerId,
            arguments: Dict[str, Any],
            runtime_context: Any,
        ) -> LlmCommandResultDto:
            try:
                resolved = argument_resolver.resolve_args(
                    tool_name, arguments, runtime_context,
                )
            except ToolArgumentResolutionException as e:
                return LlmCommandResultDto(
                    success=False,
                    message=str(e),
                    error_code=getattr(e, "error_code", "INVALID_TARGET_LABEL"),
                    remediation=(
                        "所持アイテム表示にある I1/I2 等のラベルを指定してください。"
                        "ラベルが見つからない場合、そのアイテムは現在所持していない可能性があります。"
                    ),
                )
            if resolved is None:
                # resolver dispatch table に tool_name が登録されていない =
                # 設計違反。raw 渡しで executor に押し付けるとエラー発生源が
                # 分かりにくくなる (executor 内 KeyError or INVALID_ARGUMENT
                # に化ける)。明示的な error_code で即 surface する。
                logger.error(
                    "argument resolver returned None for tool_name=%s; "
                    "dispatch table is missing this tool (design violation)",
                    tool_name,
                )
                return LlmCommandResultDto(
                    success=False,
                    message=(
                        f"ツール '{tool_name}' の引数解決が実装されていません "
                        "(設計バグ)。"
                    ),
                    error_code="RESOLVER_DISPATCH_MISSING",
                    remediation=(
                        "別のツールを試してください。同じツールを連打しても "
                        "解決しません (フレームワーク側の修正が必要)。"
                    ),
                )
            return raw_handler(int(player_id.value), resolved)

        return _handler

    def attach_action_failed_wiring(
        self,
        emitter: ActionFailedObservationEmitter,
        generator: IntentIdGenerator,
    ) -> None:
        """二段構築の 2 段目: ActionFailed 観測の依存を後付け注入する。

        ``create_session`` でのみ呼ぶ想定。両方セットで呼ぶことで、
        emitter だけ刺さって generator が None という中間状態を避ける。
        """
        self.action_failed_emitter = emitter
        self.intent_id_generator = generator

    def run_turn(self, player_id: PlayerId) -> LlmCommandResultDto:
        """1 turn を Phase A (snapshot + LLM) + Phase B (世界 mutation) で実行。

        Step 1 並列化 (#346) 以降、両 phase は分離されているが、本メソッドは
        旧来の同期挙動 (1 player 完結) を維持するための wrapper。並列化は
        `_EscapeGameLlmTurnTrigger.run_scheduled_turns` 側で行う。
        """
        phase_a = self.run_phase_a(player_id)
        return self.run_phase_b(phase_a)

    def run_phase_a(self, player_id: PlayerId) -> _LlmPhaseAResult:
        """Phase A: snapshot 構築 + LLM 呼び出し。並列化可能。

        - build_full_prompt は observation buffer を drain するが、buffer は
          player_id keyed で別プレイヤー間で衝突しないので並列実行できる
        - LLM 呼び出しはブロッキング HTTP。GIL を解放するので thread 並列で
          実時間を稼げる
        - 例外は捕まえて結果に詰める (Phase B 側で LlmCommandResultDto 化)
        """
        prompt = self.runtime.build_full_prompt(player_id)
        tools_payload = [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self.runtime.get_tool_definitions()
        ]
        # 実験 #356 対応: LLM 1 呼び出しごとに metrics (wall_latency / tokens / TPS)
        # を trace に流す。Phase A の中で player_id / tick の context を sink に閉
        # じ込めて、後で集計スクリプトが per-agent / per-model 分布を出せるよう
        # にする。
        metrics_sink = self._build_llm_metrics_sink(player_id)
        try:
            tool_call = self.llm_client.invoke(
                prompt["messages"], tools_payload, "required",
                metrics_sink=metrics_sink,
            )
            return _LlmPhaseAResult(
                player_id=player_id,
                prompt=prompt,
                tools_payload=tools_payload,
                tool_call=tool_call,
                exception=None,
            )
        except Exception as exc:  # review HIGH 2: KeyboardInterrupt / SystemExit / GeneratorExit は伝播させる
            logger.exception(
                "Phase A llm invoke failed for player_id=%s",
                player_id.value,
            )
            return _LlmPhaseAResult(
                player_id=player_id,
                prompt=prompt,
                tools_payload=tools_payload,
                tool_call=None,
                exception=exc,
            )

    def run_phase_b(self, phase_a: _LlmPhaseAResult) -> LlmCommandResultDto:
        """Phase B: Phase A の結果を受けて世界 mutation を適用する。

        serial 実行が前提 (世界 mutation / 観測 broadcast / trace 順序が決定論
        的に並ぶように、Phase A の to_run 順で呼ぶ)。
        """
        player_id = phase_a.player_id
        if phase_a.exception is not None:
            # Phase A で LLM 呼び出しが落ちた場合の救済 path。
            result = LlmCommandResultDto(
                success=False,
                message=f"LLM 呼び出しに失敗しました: {phase_a.exception}",
                error_code="LLM_API_FAILED",
                remediation="リトライするか、API キー / network を確認してください。",
                should_reschedule=False,
                was_no_op=True,
            )
            self.runtime._record_action_result(
                player_id,
                "LLM API 呼び出し",
                result.message,
                tool_name="llm_api_failed",
                success=False,
                error_code="LLM_API_FAILED",
            )
            return result
        prompt = phase_a.prompt
        messages = prompt["messages"]
        tool_call = phase_a.tool_call
        if tool_call is None:
            result = LlmCommandResultDto(
                success=False,
                message="LLM がツールを返しませんでした。",
                error_code="NO_TOOL_CALL",
                remediation="必ずいずれか 1 つのツールを呼び出してください。",
                should_reschedule=False,
                was_no_op=True,
            )
            self.runtime._record_action_result(
                player_id,
                "LLM API 呼び出し",
                result.message,
                tool_name="no_tool_call",
                success=False,
                error_code="NO_TOOL_CALL",
            )
            return result

        name = str(tool_call.get("name", ""))
        arguments = self._coerce_arguments(tool_call.get("arguments"))
        # Phase 1d: ACTION 自動 trace (実行前)。runtime に trace_recorder が
        # 注入されていれば記録。LlmAgentOrchestrator 経路を通らない escape_game
        # 専用 wiring のための補完。
        trace_recorder = getattr(self.runtime, "trace_recorder", None)
        current_tick: Optional[int] = None
        if trace_recorder is not None:
            try:
                current_tick = int(self.runtime.current_tick())
            except Exception:
                current_tick = None
            try:
                trace_recorder.record(
                    "action",
                    tick=current_tick,
                    player_id=int(player_id.value),
                    tool=name,
                    arguments=arguments,
                )
            except Exception:
                logger.exception("trace_recorder.record(action) failed")
        # multi-tick action 中の中断ロジック: busy 中に "heavy" tool が来たら、
        # まず travel をキャンセルして agent を現在地に着地させてから tool を
        # 実行する (free tool: speech / memo / examine / wait は中断せず通す)。
        # LLM への surface は snapshot の agent_status section で既に通知済み。
        # Review HIGH 1 対応: 中断前の nav_state を snapshot して、tool 実行が
        # 失敗したら travel を復元する (= 「失敗したのに移動が消える」を防ぐ)。
        was_interrupted, nav_snapshot = self._maybe_interrupt_busy(
            player_id, name
        )
        try:
            result = self._execute_tool(
                player_id,
                name,
                arguments,
                prompt["tool_runtime_context"],
            )
        except Exception as exc:
            # PR 6 (#227 / Agent A #7): 旧コードは stack trace を握りつぶしていた
            # ため、何が起きたか追跡不能だった。logger.exception で trace を残す。
            logger.exception(
                "_execute_tool failed for player_id=%s tool=%s arguments=%s",
                player_id.value,
                name,
                arguments,
            )
            result = LlmCommandResultDto(
                success=False,
                message=f"LLM ツール実行に失敗しました: {exc}",
                error_code="LLM_TOOL_EXECUTION_FAILED",
                remediation="現在の状況に表示されたラベルと利用可能な action_name を確認してください。",
            )
        # Review HIGH 1 対応: tool が失敗したら travel を復元する。
        # 成功時のみ中断確定。失敗時は「travel 継続中だが今 tick は別行動を
        # 試みて失敗した」状態に戻す (LLM が次 tick で travel を再開できる)。
        rolled_back = False
        if not result.success and nav_snapshot is not None:
            self._restore_nav_state(player_id, nav_snapshot)
            rolled_back = True
        # 中断が起きていれば result.message に「移動を中断した」prefix を付与。
        # 観測としても次 tick で agent_status の busy=False が読めるので二重保険。
        # ロールバックされた場合は別文面: travel は維持されたまま。
        if was_interrupted and not rolled_back:
            result = dataclass_replace(
                result,
                message="進行中の移動を中断して新しい行動を選択した。 " + result.message,
            )
        elif rolled_back:
            result = dataclass_replace(
                result,
                message="行動は失敗したため、進行中の移動はそのまま継続している。 " + result.message,
            )
        # PR 5 (#227): memo 完了 hint で result.message を augment する。
        # memo_* ツール自身の実行直後は hint を出さない (冗長 / 自己参照ループ
        # 防止)。本家経路 (LlmAgentOrchestrator._maybe_augment_with_memo_hint)
        # と同等。
        if (
            self.memo_completion_hint_service is not None
            and name
            and name not in (TOOL_NAME_TODO_ADD, TOOL_NAME_TODO_LIST, TOOL_NAME_TODO_COMPLETE)
        ):
            try:
                action_summary = f"{name}({json.dumps(arguments, ensure_ascii=False)})"
                # Issue #240 後続: detect() を直接呼び、hint 発火時に trace に
                # MEMO_HINT を emit。これにより実 LLM 試走で「hint が出たか / その後
                # LLM が memo_done を呼んだか」を trace 経由で追える。
                hint = self.memo_completion_hint_service.detect(
                    player_id, action_summary, result.message
                )
                if hint is not None:
                    augmented_message = result.message + hint.to_hint_text()
                    result = dataclass_replace(result, message=augmented_message)
                    if trace_recorder is not None:
                        try:
                            from ai_rpg_world.application.trace import TraceEventKind
                            trace_recorder.record(
                                TraceEventKind.MEMO_HINT,
                                tick=current_tick,
                                player_id=int(player_id.value),
                                memo_id=hint.memo.id,
                                memo_content=hint.memo.content,
                                similarity=round(hint.similarity, 4),
                                tool_name=name,
                            )
                        except Exception:
                            logger.exception("trace_recorder.record(memo_hint) failed")
            except Exception:
                logger.exception("memo_completion_hint_service.detect failed")
        skip_duplicate_action_log = result.success and name in (
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
        )
        if not skip_duplicate_action_log:
            self.runtime._record_action_result(
                player_id,
                f"{name}({json.dumps(arguments, ensure_ascii=False)})",
                result.message,
                tool_name=name,
                success=result.success,
                error_code=result.error_code,
            )
        if trace_recorder is not None:
            try:
                trace_recorder.record(
                    "action_result",
                    tick=current_tick,
                    player_id=int(player_id.value),
                    tool=name,
                    success=result.success,
                    error_code=result.error_code,
                    result_summary=result.message,
                )
            except Exception:
                logger.exception("trace_recorder.record(action_result) failed")
        # PR 4 (#227): 同一ツール連打を検知し警告観測を注入する。
        # action_result の記録後に呼ぶことで、失敗を繰り返すケースも検知対象
        # に入る。閾値超過時は次ターンの prompt 構築時に observation buffer
        # から drain されて LLM に警告が届く。
        if name:
            try:
                self.tool_call_loop_guard.record_and_check(
                    player_id,
                    name,
                    arguments,
                )
            except Exception:
                logger.exception("tool_call_loop_guard.record_and_check failed")
        # 失敗 DTO のとき ActionFailed 観測を該当プレイヤーへ投入する。
        # post-hoc に Intent VO を構築し observer に渡す (intent queue 経由は
        # しない — 即時 path で意味のある最小 wire-in)。LLM API レベルや
        # 配線エラーは emitter 側で除外される。
        if not result.success:
            self._emit_action_failed_observation(player_id, name, arguments, result)
        return result

    def _emit_action_failed_observation(
        self,
        player_id: PlayerId,
        tool_name: str,
        arguments: dict[str, Any],
        result: LlmCommandResultDto,
    ) -> None:
        if self.action_failed_emitter is None or self.intent_id_generator is None:
            return
        # 空 tool_name は LLM 出力の欠陥 (例: ``{"name": ""}``)。Intent VO は
        # 非空 str を要求するため "unknown" 等で穴埋めすると観測の tool_name
        # フィールドが false-positive な値で汚れる。診断用に warning を残し、
        # 観測そのものは emit しない (LLM API レベル失敗の扱いに準じる)。
        if not tool_name:
            logger.warning(
                "Skipping ActionFailed emission: empty tool_name from LLM "
                "(player=%s error_code=%s)",
                player_id.value,
                result.error_code,
            )
            return
        try:
            current_tick_value = int(self.runtime.current_tick())
            tick = WorldTick(current_tick_value)
            intent = Intent(
                intent_id=self.intent_id_generator.next_id(),
                player_id=player_id,
                tool_name=tool_name,
                arguments=dict(arguments),
                phase=phase_for_tool(tool_name),
                submitted_at_tick=tick,
                complete_at_tick=tick,
            )
            self.action_failed_emitter.on_resolution_failure(intent, result)
        except Exception:
            # observer 発火が turn 結果を倒さないよう吸収 (best-effort)。
            logger.exception(
                "Failed to emit ActionFailed observation for player=%s tool=%s",
                player_id.value,
                tool_name,
            )

    def _build_llm_metrics_sink(
        self, player_id: PlayerId
    ) -> Optional[Any]:
        """Phase A の LLM 呼び出し metrics を trace に流す sink を構築する。

        trace_recorder が無い (= テスト等) なら None を返して、litellm 側で
        no-op になる。

        Review HIGH 2 対応: current_tick は **record 時点** で取得する
        (sink 構築時の固定値だと、遅い LLM 呼び出しが tick 境界を跨いだとき
        stale な tick が記録される)。
        Review MEDIUM 後続: inner class の動的定義を避け、module-level の
        `_LlmMetricsTraceSink` クラスを再利用する (parallel 経路の hot path)。
        """
        trace_recorder = getattr(self.runtime, "trace_recorder", None)
        if trace_recorder is None:
            return None
        return _LlmMetricsTraceSink(
            trace_recorder=trace_recorder,
            runtime=self.runtime,
            player_id=player_id,
        )

    # busy 中に "free" 扱いして中断を発火しない tool 群。
    # 軽い行動 (発話 / メモ / 観察 / 待機) は travel と並行できる。
    # 重い tool (travel_to / interact / use_item / attack / drop / pickup /
    # give / prepare_action / set_sub_location) は busy を中断する。
    #
    # 注: `set_sub_location` を heavy 側に含めるのは、travel 中に
    # `PlayerSpotNavigationState.with_sub_location` が domain 例外を投げる
    # (= sub_location 変更は travel 完了後でないと意味がない) ため。中断して
    # から sub_location 変更を試みる semantics が一貫している。
    # 注: leg 途中で中断したときの `current_spot_id` は出発地のままになる
    # (`PlayerSpotNavigationState.advance_one_world_tick` が leg 完了時のみ
    # 更新するため)。物理的に「edge の途中で立ち止まる」状態は表現せず、
    # 「最後に通過した spot で停止」semantics を取る (graph 上の entity 位置
    # も同じ spot に居続けるので整合する)。
    _BUSY_FREE_TOOLS: frozenset[str] = frozenset({
        TOOL_NAME_SPEECH,
        TOOL_NAME_SPOT_GRAPH_LISTEN,
        TOOL_NAME_SPOT_GRAPH_WAIT,
        TOOL_NAME_SPOT_GRAPH_EXPLORE,  # 周囲を見る (移動はしない)
        TOOL_NAME_TODO_ADD,
        TOOL_NAME_TODO_LIST,
        TOOL_NAME_TODO_COMPLETE,
    })

    def _maybe_interrupt_busy(
        self, player_id: PlayerId, tool_name: str
    ) -> tuple[bool, Optional[PlayerSpotNavigationState]]:
        """重い tool が来たら travel をキャンセルして agent を現在地に着地させる。

        Review HIGH 1 対応: 中断前の nav_state を snapshot として返す。
        tool が失敗した場合に呼び出し側が `_restore_nav_state` で元に戻せる。

        Returns:
            (was_interrupted, nav_state_snapshot)。
            was_interrupted=False のとき snapshot は None。
        """
        if not tool_name or tool_name in self._BUSY_FREE_TOOLS:
            return False, None
        repo = getattr(self.runtime, "_player_status_repo", None)
        if repo is None:
            return False, None
        status = repo.find_by_id(player_id)
        if status is None or status.spot_navigation_state is None:
            return False, None
        nav = status.spot_navigation_state
        if not nav.is_traveling:
            return False, None
        # snapshot を取ってから current_spot で at_rest 状態に上書きする
        # (= 中断 / 残り leg 破棄)。snapshot は immutable な dataclass なので
        # コピー不要。
        nav_snapshot = nav
        status.set_spot_navigation_state(
            PlayerSpotNavigationState.at_rest(nav.current_spot_id)
        )
        repo.save(status)
        logger.info(
            "Travel interrupted for player_id=%s by tool=%s (was at leg %d of %d)",
            int(player_id.value),
            tool_name,
            nav.leg_index,
            len(nav.leg_connection_ids),
        )
        return True, nav_snapshot

    def _restore_nav_state(
        self,
        player_id: PlayerId,
        nav_snapshot: PlayerSpotNavigationState,
    ) -> None:
        """Review HIGH 1 対応: tool が失敗したら nav_state を snapshot に戻す。

        「中断 → tool 失敗 → 移動が消える」を避けるためのロールバック。
        """
        repo = getattr(self.runtime, "_player_status_repo", None)
        if repo is None:
            return
        status = repo.find_by_id(player_id)
        if status is None:
            return
        status.set_spot_navigation_state(nav_snapshot)
        repo.save(status)
        logger.info(
            "Travel restored for player_id=%s (tool failed, nav_state rolled back)",
            int(player_id.value),
        )

    def _coerce_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str) and raw_arguments:
            try:
                parsed = json.loads(raw_arguments)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    def _execute_tool(
        self,
        player_id: PlayerId,
        name: str,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        """ツール名から対応するハンドラを選んで実行する。

        PR 7 (#227): 旧コードは 240 行の if/elif ディスパッチだった。本家経路
        ``ToolCommandMapper.execute`` と構造を合わせるため、ツール名→ハンドラ
        メソッドの ``_tool_handlers`` テーブル経由のディスパッチに改めた。
        各ハンドラは ``(player_id, arguments, runtime_context) -> LlmCommandResultDto``。
        未登録のツールは UNSUPPORTED_TOOL を返す。

        将来の経路統一 (本家 ``LlmAgentOrchestrator`` への移行) では、
        ``runtime.do_*`` ラッパー呼出しを本家の ``_argument_resolvers`` +
        ``executors`` 経由に差し替える方向に進める。本テーブルがその移行先
        になる。
        """
        handler = self._tool_handlers.get(name)
        if handler is None:
            return LlmCommandResultDto(
                success=False,
                message=f"未対応のツールです: {name}",
                error_code="UNSUPPORTED_TOOL",
            )
        return handler(player_id, arguments, runtime_context)

    # ── per-tool handlers (PR 7) ──

    def _handle_explore(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        targets = getattr(runtime_context, "targets", {})
        result = self.runtime.do_explore(player_id)
        if result.discovery_descriptions:
            message = "発見: " + " / ".join(result.discovery_descriptions)
        else:
            # F2: 「新しい発見はなかった」だけだと LLM が「部屋に何もない」と
            # 誤解し interact しなくなる癖がある。spot view に既に表示されて
            # いる可視オブジェクトを併記して、LLM の "見えない" 誤認を防ぐ。
            visible_objects = _list_object_labels(targets)
            if visible_objects:
                message = (
                    "新しい発見はなかった。"
                    f"既に見えているオブジェクト: {visible_objects}"
                    " (interact するにはこのラベルを object_label に指定する)"
                )
            else:
                message = "新しい発見はなかった (この場所に interactable なオブジェクトは無い)"
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            arguments,
            LlmCommandResultDto(success=True, message=message),
        )

    def _handle_travel_to(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        # Issue #276 経路二重化解消: 本家 resolver と同じ
        # ``resolve_destination_target`` で label を解決する。崩れ表現
        # (連結文字列 / 括弧 / 矢印) の吸収もここに集約される。
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            resolve_destination_target,
        )
        from ai_rpg_world.application.llm.services._resolver_helpers import (
            ToolArgumentResolutionException,
        )

        targets = getattr(runtime_context, "targets", {})
        label = str(arguments.get("destination_label", ""))
        try:
            target = resolve_destination_target(label, runtime_context)
        except ToolArgumentResolutionException as e:
            valid_destinations = _list_destination_labels(targets)
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"移動先が見つかりません: {label}。"
                    f"有効な destination_label: "
                    f"{valid_destinations or '(この場所からの移動先なし)'}"
                ),
                error_code=e.error_code,
                remediation=(
                    "destination_label には現在の状況に表示された S1, S2 等の "
                    "ラベル、またはスポット名 (例: 閲覧室) を指定してください。"
                ),
            )
        destination_id = self.runtime.id_mapper.get_str("spot", target.spot_id)
        self.runtime.do_move(player_id, destination_id)
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            arguments,
            LlmCommandResultDto(
                success=True,
                message=f"{target.display_name}へ移動しました。",
            ),
        )

    def _handle_interact(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        # Issue #276 経路二重化解消: 本家 resolver と同じ
        # ``resolve_object_target`` で label を解決。
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            resolve_object_target,
        )
        from ai_rpg_world.application.llm.services._resolver_helpers import (
            ToolArgumentResolutionException,
        )

        targets = getattr(runtime_context, "targets", {})
        label = str(arguments.get("object_label", ""))
        action_name = str(arguments.get("action_name", ""))
        try:
            target = resolve_object_target(label, runtime_context)
        except ToolArgumentResolutionException as e:
            valid_objects = _list_object_labels(targets)
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"オブジェクトラベルが見つかりません: {label}。"
                    f"有効な object_label: "
                    f"{valid_objects or '(この場所に interactable なオブジェクトなし)'}"
                ),
                error_code=e.error_code,
                remediation=(
                    "object_label には現在の状況に表示された OBJ1, OBJ2 等の "
                    "ラベル (display name ではなく) を指定してください。"
                ),
            )
        object_id = self.runtime.id_mapper.get_str("object", target.world_object_id)
        # N2: precondition 失敗 (= scenario JSON の failure_message) を generic
        # "LLM ツール実行に失敗しました" に潰さず、failure_message そのものを
        # surface する。さらに「枯渇」っぽい文言なら retry を抑える remediation
        # を添える (= 同じ object に再度同 action_name を投げない指示)。
        try:
            result = self.runtime.do_interact(player_id, object_id, action_name)
        except InteractionNotAllowedException as exc:
            reason = str(exc) or "前提条件を満たさない"
            return LlmCommandResultDto(
                success=False,
                message=f"行動が拒否された: {reason}",
                error_code="INTERACTION_PRECONDITION_FAILED",
                remediation=_interact_remediation_for_reason(reason),
            )
        except InteractionNotFoundException:
            # 実験 #26 で発覚: LLM が ad-hoc に "search" / "examine" / "interact"
            # 等の action_name を発明して呼び、generic LLM_TOOL_EXECUTION_FAILED
            # に化けていた (reason が "search on 2" のような ID 表示で意味不明)。
            # 当該 object で実際に使える action 一覧を提示して LLM を正規の
            # action_name に誘導する。
            available = _list_object_interactions(
                self.runtime, object_id,
            )
            avail_str = ", ".join(available) if available else "(なし)"
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"このオブジェクトには '{action_name}' という操作がありません。"
                    f"利用可能な操作: {avail_str}"
                ),
                error_code="INTERACTION_ACTION_NOT_FOUND",
                remediation=(
                    "action_name には現在の状況に表示されたオブジェクトの "
                    "「使える操作」(例: gather / examine 等の定義済 action) を"
                    "そのまま指定してください。汎用名 (search / interact) は"
                    "通常 scenario に存在しません。"
                ),
            )
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            arguments,
            LlmCommandResultDto(
                success=True,
                message="; ".join(result.messages) if result.messages else "完了",
            ),
        )

    def _handle_listen(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        # tool catalog に LISTEN_DEFINITION があるのに dispatch が無く
        # UNSUPPORTED_TOOL に化けていた配線漏れ (Issue #154 デモ) を修正。
        # runtime.do_listen が SpotSoundHeardEvent を発火し、observation
        # pipeline で本人にだけ観測が届く (formatter が prose を構築するので、
        # ここでは件数ベースのサマリだけ返す)。
        try:
            event_count = self.runtime.do_listen(player_id)
        except Exception:
            logger.exception(
                "do_listen failed for player=%s", player_id.value
            )
            return LlmCommandResultDto(
                success=False,
                message="耳を澄ますに失敗しました。",
                error_code="LLM_TOOL_EXECUTION_FAILED",
                remediation="やり直すか別のツールを使ってください。",
            )
        if event_count == 0:
            base_message = "耳を澄ましたが、何も聞こえなかった。"
        elif event_count == 1:
            base_message = "耳を澄ました。周囲の音が観測として届いた。"
        else:
            base_message = (
                f"耳を澄ました。{event_count} 箇所からの音が観測として届いた。"
            )
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_LISTEN,
            arguments,
            LlmCommandResultDto(success=True, message=base_message),
        )

    def _handle_wait(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        del runtime_context  # unused — wait は targets を見ない
        reason = str(arguments.get("reason", "")).strip()
        tick = self.runtime.do_wait(player_id, reason=reason)
        suffix = f"（理由: {reason}）" if reason else ""
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_WAIT,
            arguments,
            LlmCommandResultDto(
                success=True,
                message=f"待機して時間が進んだ: tick={tick}{suffix}",
            ),
        )

    def _handle_speech(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        """Issue #264 後続: 単一 speech_speak tool の dispatch。

        ``channel`` 引数 (whisper/say/shout) で挙動を分岐する。
        - whisper: ``target_label`` 必須 (同 spot 内の特定プレイヤー)
        - say: 同 spot + 隣接 (1 hop)
        - shout: 同 spot + 隣接 + 2 hop
        """
        from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import (
            SPEECH_CHANNEL_SAY,
            SPEECH_CHANNEL_SHOUT,
            SPEECH_CHANNEL_VALUES,
            SPEECH_CHANNEL_WHISPER,
        )
        from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

        channel_str = str(arguments.get("channel", "")).lower()
        if channel_str not in SPEECH_CHANNEL_VALUES:
            return LlmCommandResultDto(
                success=False,
                message=(
                    f"channel が不正です: {channel_str!r}。"
                    f"{list(SPEECH_CHANNEL_VALUES)!r} のいずれかを指定してください。"
                ),
                error_code="INVALID_SPEECH_CHANNEL",
            )
        content = str(arguments.get("content", "")).strip()
        if not content:
            return LlmCommandResultDto(
                success=False,
                message="発話内容 (content) が空です。",
                error_code="INVALID_SPEECH_CONTENT",
            )

        channel_map = {
            SPEECH_CHANNEL_WHISPER: SpeechChannel.WHISPER,
            SPEECH_CHANNEL_SAY: SpeechChannel.SAY,
            SPEECH_CHANNEL_SHOUT: SpeechChannel.SHOUT,
        }
        channel_enum = channel_map[channel_str]

        target_player_id_obj: Optional[PlayerId] = None
        if channel_enum == SpeechChannel.WHISPER:
            targets = getattr(runtime_context, "targets", {})
            target_label = str(arguments.get("target_label", ""))
            target = self._resolve_whisper_target(target_label, targets)
            if target is None or target.player_id is None:
                valid_players = _list_player_labels(targets)
                detail = (
                    f"target_label={target_label!r} が見つかりません。"
                    f"有効な target_label: {valid_players or '(同 spot に他プレイヤーなし)'}"
                )
                return LlmCommandResultDto(
                    success=False,
                    message=f"囁きを送れませんでした: {detail}",
                    error_code="INVALID_WHISPER",
                    remediation=(
                        "channel=whisper のときは target_label に同じスポット内の "
                        "プレイヤーラベル (P1, P2 等) または相手の名前 (例: リン) "
                        "を指定してください。"
                    ),
                )
            target_player_id_obj = PlayerId(target.player_id)

        self.runtime.do_speech(player_id, content, channel_enum, target_player_id_obj)

        # audience フィードバック付き message
        action_verb = {
            SpeechChannel.WHISPER: "囁いた",
            SpeechChannel.SAY: "発言した",
            SpeechChannel.SHOUT: "叫んだ",
        }[channel_enum]
        audience_suffix = self._build_audience_summary(
            player_id, channel_enum, target_player_id_obj
        )
        return LlmCommandResultDto(
            success=True,
            message=f"{action_verb}: {content}{audience_suffix}",
        )

    def _resolve_whisper_target(
        self,
        target_label: str,
        targets: dict[str, Any],
    ) -> Optional[Any]:
        """[delegating] 本家 resolver の ``resolve_player_target`` への薄い
        ラッパー。後方互換用に残す (callers + tests が直接呼んでいる)。

        Issue #276: 旧実装で `_normalize_label_candidates` を使った独自経路
        だったが、resolver 側に統合した。
        """
        from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
            resolve_player_target,
        )
        # 既存呼び出しは targets 単体を渡してくるので、runtime_context を
        # 偽装する単純な namespace で fallback の resolver API に合わせる。
        rtc = type("_RTCStub", (), {"targets": targets})()
        return resolve_player_target(target_label, rtc)  # type: ignore[arg-type]

    def _build_audience_summary(
        self,
        player_id: PlayerId,
        channel: Any,
        target_player_id: Optional[PlayerId],
    ) -> str:
        """speech 発火直後の audience 情報を message に追記する suffix を返す。

        Issue #264 B1: agent に「あなたの声が届いた範囲」を明示することで、
        返事の有無を待たずに次手を考えられるようにする。
        channel ごとに 0 audience 時の次手提案も含める。
        """
        if self.speech_audience_resolver is None:
            return ""
        from ai_rpg_world.application.speech.services.audience_feedback import (
            audience_summary_text,
        )
        try:
            members = self.speech_audience_resolver.resolve_audience_with_clarity(
                speaker_player_id=int(player_id.value),
                channel=channel,
                target_player_id=(
                    int(target_player_id.value)
                    if target_player_id is not None
                    else None
                ),
            )
        except Exception:
            logger.exception("speech_audience_resolver.resolve_audience_with_clarity failed")
            return ""
        return f"（{audience_summary_text(channel, members)}）"

    def _handle_set_sub_location(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        del player_id, arguments, runtime_context
        return LlmCommandResultDto(
            success=False,
            message="サブロケーション変更は脱出ランタイムでは未対応です。",
            error_code="UNSUPPORTED_TOOL",
        )

    def _make_auxiliary_tool_handler(
        self, tool_name: str
    ) -> Callable[[PlayerId, dict[str, Any], Any], LlmCommandResultDto]:
        """TODO/memo ツール用のハンドラを tool_name 固定で返す。

        NOTE: pure_spot_graph mode (B-4 / Issue #155) では TODO/memo ツールは
        LLM の tools リストに含まれないため、通常到達しない。安全側のフォール
        バックとして残し、デフォルト構成で memo を使う際の経路を維持する。
        """

        def handler(
            player_id: PlayerId,
            arguments: dict[str, Any],
            runtime_context: Any,
        ) -> LlmCommandResultDto:
            del runtime_context
            return self.runtime.run_llm_auxiliary_tool(
                player_id, tool_name, arguments
            )

        return handler

    def _time_label(self) -> str:
        # 旧実装は `(tick * 5) % (24*60)` で「1 tick = 5 分」を仮定していたが、
        # 漂流島 v2 で 1 tick = 1 時間スケールに統一されて以降、tick 140 で
        # 11:40 表示 (実際は day 5 20:00) のように LLM プロンプトに渡る時刻が
        # 嘘になっていた。runtime 側に day_night ベースの正規実装
        # (escape_game_runtime._time_label) があるのでそれに委譲する。
        runtime_label = getattr(self.runtime, "_time_label", None)
        if callable(runtime_label):
            return runtime_label()
        # フォールバック: runtime が _time_label を持たない場合 (将来の別 runtime)、
        # 1 tick = 1 時間 / 24 ticks_per_day を仮定して計算する。
        tick = self.runtime.current_tick()
        hours = tick % 24
        return f"深夜 {hours}:00" if hours < 6 else f"{hours}:00"


@dataclass
class _SessionState:
    """Lightweight bookkeeping for a running game session."""

    session_id: str
    world_id: str
    world_title: str
    character_ids: list[str]
    status: str  # "running" | "paused" | "ended"
    created_at: str
    speed_multiplier: float = 1.0

    runtime: Any = field(default=None, repr=False)
    llm_wiring: Any = field(default=None, repr=False)
    pending_llm_turns: set[int] = field(default_factory=set, repr=False)


@dataclass
class GameRuntimeManager:
    """Facade consumed by all API routers."""

    scenarios_dir: Path = field(default_factory=lambda: Path("data/scenarios"))
    characters_path: Path = field(default_factory=lambda: Path("data/characters.json"))

    _scenario_cache: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    _characters: Dict[str, CharacterDetailResponse] = field(
        default_factory=dict, repr=False
    )
    _characters_loaded: bool = field(default=False, repr=False)
    _sessions: Dict[str, _SessionState] = field(
        default_factory=dict, repr=False
    )
    _chat_histories: Dict[str, list[ChatMessageResponse]] = field(
        default_factory=dict, repr=False
    )
    # 長走時の保険:
    # - tick thread と chat 送信 thread が同時に dict を触る (compound op race)
    # - 履歴に上限なしで永遠に append されてメモリが膨らむ
    # の 2 つを 1 つの lock + cap で潰す。200 件はキャラとの最近の会話を
    # 復元するのに十分で、それ以上は viewer 側で必要なら別 store に永続化
    # する設計を想定。
    _chat_history_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )
    _CHAT_HISTORY_MAX_PER_KEY: int = 200

    # ── Worlds ──

    def _load_scenario_raw(self, world_id: str) -> Optional[Dict[str, Any]]:
        if world_id in self._scenario_cache:
            return self._scenario_cache[world_id]
        path = self.scenarios_dir / f"{world_id}.json"
        if not path.exists():
            return None
        raw = _read_scenario_metadata(path)
        if raw is not None:
            self._scenario_cache[world_id] = raw
        return raw

    def list_available_worlds(self) -> list[WorldSummaryResponse]:
        worlds: list[WorldSummaryResponse] = []
        if not self.scenarios_dir.exists():
            return worlds
        for path in sorted(self.scenarios_dir.glob("*.json")):
            raw = self._load_scenario_raw(path.stem)
            if raw is None:
                continue
            meta = raw.get("metadata", {})
            worlds.append(
                WorldSummaryResponse(
                    id=meta.get("id", path.stem),
                    title=meta.get("title", path.stem),
                    description=meta.get("description", ""),
                    theme=meta.get("theme", ""),
                    difficulty=meta.get("difficulty", "medium"),
                    estimated_ticks=int(meta.get("estimated_ticks", 100)),
                    tags=list(meta.get("tags", [])),
                )
            )
        return worlds

    def get_world_detail(self, world_id: str) -> Optional[WorldDetailResponse]:
        raw = self._load_scenario_raw(world_id)
        if raw is None:
            return None
        meta = raw.get("metadata", {})
        return WorldDetailResponse(
            id=meta.get("id", world_id),
            title=meta.get("title", world_id),
            description=meta.get("description", ""),
            theme=meta.get("theme", ""),
            difficulty=meta.get("difficulty", "medium"),
            estimated_ticks=int(meta.get("estimated_ticks", 100)),
            tags=list(meta.get("tags", [])),
            spots_count=len(raw.get("spots", [])),
            items_count=len(raw.get("item_specs", [])),
            connections_count=len(raw.get("connections", [])),
        )

    # ── Characters ──

    def _load_characters(self) -> None:
        if self._characters_loaded:
            return
        self._characters_loaded = True
        if not self.characters_path.exists():
            self._characters = {}
            return
        try:
            with open(self.characters_path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read characters %s: %s", self.characters_path, exc)
            self._characters = {}
            return

        entries = raw.get("characters", []) if isinstance(raw, dict) else []
        characters: dict[str, CharacterDetailResponse] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            try:
                character = CharacterDetailResponse(**entry)
            except Exception as exc:
                logger.warning("Skipping invalid character entry: %s", exc)
                continue
            characters[character.id] = character
        self._characters = characters

    def _save_characters(self) -> None:
        self.characters_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "characters": [
                character.model_dump()
                for character in sorted(
                    self._characters.values(), key=lambda c: c.name
                )
            ]
        }
        tmp_path = self.characters_path.with_suffix(self.characters_path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        tmp_path.replace(self.characters_path)

    def list_characters(self) -> list[CharacterSummaryResponse]:
        self._load_characters()
        return [
            CharacterSummaryResponse(
                id=character.id,
                name=character.name,
                age_image=character.age_image,
                personality_tags=character.personality_tags,
                portrait_url=character.portrait_url,
                icon_url=character.icon_url,
            )
            for character in sorted(self._characters.values(), key=lambda c: c.name)
        ]

    def get_character(self, character_id: str) -> Optional[CharacterDetailResponse]:
        self._load_characters()
        return self._characters.get(character_id)

    def create_character(
        self, request: CharacterCreateRequest
    ) -> CharacterDetailResponse:
        self._load_characters()
        cid = uuid.uuid4().hex[:8]
        while cid in self._characters:
            cid = uuid.uuid4().hex[:8]
        character = CharacterDetailResponse(
            id=cid,
            name=request.name,
            personality_tags=request.personality_tags,
            first_person=request.first_person,
            appearance=request.appearance,
            speech_samples=request.speech_samples,
            fragmented_memory=request.fragmented_memory,
            values=request.values,
            strengths=request.strengths,
            weaknesses=request.weaknesses,
            interpersonal_tendency=request.interpersonal_tendency,
            behavioral_rules=list(request.behavioral_rules or ()),
        )
        self._characters[cid] = character
        self._save_characters()
        return character

    def update_character(
        self, character_id: str, request: CharacterUpdateRequest
    ) -> Optional[CharacterDetailResponse]:
        self._load_characters()
        current = self._characters.get(character_id)
        if current is None:
            return None
        data = current.model_dump()
        update_data = request.model_dump(exclude_unset=True)
        data.update({key: value for key, value in update_data.items() if value is not None})
        updated = CharacterDetailResponse(**data)
        self._characters[character_id] = updated
        self._save_characters()
        return updated

    # ── Sessions ──

    def create_session(
        self, request: SessionCreateRequest
    ) -> SessionSummaryResponse:
        scenario_path = self.scenarios_dir / f"{request.world_id}.json"
        if not scenario_path.exists():
            raise ValueError(f"World not found: {request.world_id}")

        from demos.escape_game.escape_game_runtime import (
            create_escape_game_runtime,
        )

        escape_character = None
        if request.character_ids:
            detail = self.get_character(request.character_ids[0])
            escape_character = _character_to_escape_prompt_input(detail)

        runtime = create_escape_game_runtime(
            scenario_path, escape_character=escape_character
        )
        spawn_ids = frozenset(int(sp.player_id) for sp in runtime.scenario.player_spawns)
        llm_resolver = _EscapeSpawnAllPlayersLlmResolver(spawn_player_ids=spawn_ids)
        # appender / turn_scheduler は heartbeat と ActionFailed の両方で
        # 共有する (同じ observation buffer に書き込み、同じ turn trigger を
        # 呼ぶため)。
        appender = ObservationAppender(runtime._obs_buffer)
        # 注意: llm_wiring を構築する前に turn_scheduler を作る必要がある
        # ため、最初に空の wiring を作り、それから scheduler / emitter を
        # 組み立てて wiring に注入する流れにする。
        llm_wiring = _EscapeGameLlmWiring(
            runtime=runtime, observation_buffer=runtime._obs_buffer
        )
        turn_scheduler = ObservationTurnScheduler(
            turn_trigger=llm_wiring.llm_turn_trigger,
            llm_player_resolver=llm_resolver,
        )

        def _heartbeat_llm_player_ids() -> Iterable[PlayerId]:
            return tuple(PlayerId(int(sp.player_id)) for sp in runtime.scenario.player_spawns)

        def _is_traveling(pid: PlayerId) -> bool:
            """#404 fix: 移動中の player に heartbeat を打たない判定。

            heartbeat 観測は ``schedules_turn=True`` なので、移動中に届くと
            「移動中なのに何かしようとして失敗」する空回りターンを誘発する。
            travel_stage が arrival 時に schedule_turn を打つので、移動中は
            完全に silent にしてよい。
            """
            try:
                status = runtime._player_status_repo.find_by_id(pid)
            except Exception:
                return False
            if status is None:
                return False
            nav = status.spot_navigation_state
            return nav is not None and nav.is_traveling

        heartbeat_emitter = HeartbeatObservationEmitter(
            appender,
            turn_scheduler,
            _heartbeat_llm_player_ids,
            is_traveling_provider=_is_traveling,
        )
        # ActionFailed 観測の wire: 失敗 DTO を当該プレイヤーへの観測に変換する。
        # ``intent_id_generator`` は wiring と emitter で共有しないが、wiring 側
        # で intent_id を払い出して emitter に渡す形を取る (emitter は受け取った
        # intent をそのまま使う最小役割)。
        action_failed_emitter = ActionFailedObservationEmitter(
            observation_appender=appender,
            turn_scheduler=turn_scheduler,
        )
        llm_wiring.attach_action_failed_wiring(
            emitter=action_failed_emitter,
            generator=IntentIdGenerator(),
        )
        runtime.set_simulation_llm_turn_trigger(llm_wiring.llm_turn_trigger)
        runtime.set_simulation_heartbeat_emitter(heartbeat_emitter)
        # PR 2 (#227): speech 配信は ObservationPipeline 経由になった。受信者が
        # 他者発話を聞いた場合、ObservationTurnScheduler 経由でターンを積む
        # 必要があるため、wiring 完成後の scheduler を runtime に注入する。
        runtime.set_observation_turn_scheduler(turn_scheduler)
        # #404 fix: travel 到着時に LLM ターンを再開させるためのコールバックを
        # travel_stage に注入する。is_traveling フィルタで sleep していた player
        # は、ここで schedule_turn → 次の post-tick hook で run_turn される。
        travel_stage = getattr(runtime, "_travel_stage", None)
        if travel_stage is not None and hasattr(travel_stage, "set_on_arrival"):
            travel_stage.set_on_arrival(llm_wiring.llm_turn_trigger.schedule_turn)

        sid = uuid.uuid4().hex[:12]
        title = runtime.metadata.title
        state = _SessionState(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            character_ids=request.character_ids,
            status="running",
            created_at=_utcnow_iso(),
            runtime=runtime,
            llm_wiring=llm_wiring,
        )
        self._sessions[sid] = state
        logger.info("Session %s created for world %s", sid, request.world_id)
        return SessionSummaryResponse(
            session_id=sid,
            world_id=request.world_id,
            world_title=title,
            status="running",
            current_tick=0,
            character_ids=request.character_ids,
            created_at=state.created_at,
        )

    def get_session_state(
        self, session_id: str
    ) -> Optional[SessionStateResponse]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        runtime = state.runtime
        # 1 tick = 5 分 の旧仮定を廃止。runtime の正規 _time_label に委譲する
        # (day_night サイクルから派生した正しい時刻を返す)。
        tick = runtime.current_tick() if runtime else 0
        runtime_label_fn = getattr(runtime, "_time_label", None) if runtime else None
        if callable(runtime_label_fn):
            time_label = runtime_label_fn()
        else:
            hours = tick % 24
            time_label = f"{hours}:00"

        is_ended = False
        end_result = None
        end_reason = None
        if runtime:
            result = runtime.check_game_end()
            is_ended = result.is_ended
            if is_ended:
                end_result = str(result.result) if result.result else None
                end_reason = result.reason
                state.status = "ended"

        return SessionStateResponse(
            session_id=session_id,
            status=state.status,
            current_tick=tick,
            game_time_label=time_label,
            is_ended=is_ended,
            end_result=end_result,
            end_reason=end_reason,
        )

    def pause_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "paused"
        return True

    def resume_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "running"
        return True

    def stop_session(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.status = "ended"
        return True

    def set_session_speed(
        self, session_id: str, speed_multiplier: float
    ) -> bool:
        state = self._sessions.get(session_id)
        if state is None:
            return False
        state.speed_multiplier = speed_multiplier
        return True

    def iter_running_runtimes(self) -> "Iterator[tuple[str, Any]]":
        """Yield ``(session_id, runtime)`` pairs for sessions in 'running' status.

        Used by the background tick loop to advance game time. Skips
        paused/ended sessions and sessions without a runtime (legacy stubs).

        The runtime is typed as ``Any`` because multiple runtime classes
        (escape game, future spot-graph standalone, etc.) share only the
        informal duck-typed ``advance_tick()`` contract.
        """
        for session_id, state in self._sessions.items():
            if state.status != "running" or state.runtime is None:
                continue
            yield session_id, state.runtime

    def run_scheduled_llm_turns(self, session_id: str) -> bool:
        state = self._sessions.get(session_id)
        if state is None or state.llm_wiring is None:
            return False
        turn_trigger = getattr(state.llm_wiring, "llm_turn_trigger", None)
        if turn_trigger is None or not callable(getattr(turn_trigger, "run_scheduled_turns", None)):
            return False
        turn_trigger.run_scheduled_turns()
        return True

    # ── Observations ──

    def get_spot_view(
        self,
        session_id: str,
        *,
        character_id: Optional[str] = None,
        spot_id: Optional[str] = None,
    ) -> Optional[SpotViewResponse]:
        state = self._sessions.get(session_id)
        if state is None or state.runtime is None:
            return None

        runtime = state.runtime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

        graph = runtime._spot_graph_repo.find_graph()

        if spot_id is not None:
            target_spot_int = runtime.id_mapper.get_int("spot", spot_id)
            from ai_rpg_world.domain.world.value_object.spot_id import SpotId
            target_spot_id = SpotId.create(target_spot_int)
        elif character_id is not None:
            pid_int = runtime.id_mapper.get_int("player", character_id)
            eid = EntityId.create(pid_int)
            target_spot_id = graph.get_entity_spot(eid)
        else:
            first_spawn = runtime.scenario.player_spawns[0]
            eid = EntityId.create(first_spawn.player_id)
            target_spot_id = graph.get_entity_spot(eid)

        spot_node = graph.get_spot(target_spot_id)
        interior = runtime._spot_interior_repo.find_by_spot_id(target_spot_id)

        characters: list[CharacterInSpotResponse] = []
        presence = graph.presence_at(target_spot_id)
        for eid_val in presence.present_entity_ids:
            eid_int = eid_val.value if hasattr(eid_val, "value") else int(eid_val)
            name = runtime.get_player_name(PlayerId(eid_int))
            spawn = next(
                (s for s in runtime.scenario.player_spawns if s.player_id == eid_int),
                None,
            )
            str_id = spawn.string_id if spawn else str(eid_val)
            characters.append(CharacterInSpotResponse(
                character_id=str_id,
                name=name,
            ))

        objects: list[SpotObjectResponse] = []
        if interior:
            for obj in interior.objects:
                actions = [i.action_name for i in obj.interactions]
                obj_str = _safe_get_str(runtime.id_mapper, "object", obj.object_id.value)
                objects.append(SpotObjectResponse(
                    object_id=obj_str,
                    name=obj.name,
                    description=obj.description,
                    object_type=obj.object_type.name,
                    state=dict(obj.state),
                    available_actions=actions,
                ))

        connections: list[SpotConnectionResponse] = []
        for conn in graph.iter_outgoing_connections_from(target_spot_id):
            target_node = graph.get_spot(conn.to_spot_id)
            conn_str = _safe_get_str(runtime.id_mapper, "connection", conn.connection_id.value)
            connections.append(SpotConnectionResponse(
                connection_id=conn_str,
                target_spot_id=_safe_get_str(runtime.id_mapper, "spot", conn.to_spot_id.value),
                target_spot_name=target_node.name,
                name=conn.name,
                is_passable=conn.passage.traversable,
            ))

        spot_str = _safe_get_str(runtime.id_mapper, "spot", target_spot_id.value)
        return SpotViewResponse(
            spot_id=spot_str,
            spot_name=spot_node.name,
            spot_description=spot_node.description,
            background_image_key=spot_str,
            atmosphere={
                "lighting": spot_node.atmosphere.lighting.name,
                "sound_ambient": spot_node.atmosphere.sound_ambient,
                "temperature": spot_node.atmosphere.temperature.name,
                "smell": spot_node.atmosphere.smell,
            } if spot_node.atmosphere else None,
            characters_present=characters,
            objects=objects,
            connections=connections,
        )

    def get_event_log(
        self, session_id: str, *, limit: int = 50, offset: int = 0
    ) -> Optional[EventLogResponse]:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return EventLogResponse()

    def get_inventory(
        self, session_id: str, character_id: str
    ) -> Optional[InventoryResponse]:
        state = self._sessions.get(session_id)
        if state is None or state.runtime is None:
            return None

        runtime = state.runtime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        pid_int = runtime.id_mapper.get_int("player", character_id)
        pid = PlayerId(pid_int)
        inv = runtime._player_inventory_repo.find_by_id(pid)
        items: list[InventoryItemResponse] = []
        if inv:
            from ai_rpg_world.domain.player.value_object.slot_id import SlotId

            counts: dict[int, int] = {}
            specs: dict[int, Any] = {}
            for slot_idx in range(inv._max_slots):
                iid = inv.get_item_instance_id_by_slot(SlotId(slot_idx))
                if iid is None:
                    continue
                item = runtime._item_repo.find_by_id(iid)
                if item is None:
                    continue
                sid = item.item_spec.item_spec_id.value
                counts[sid] = counts.get(sid, 0) + 1
                if sid not in specs:
                    specs[sid] = item.item_spec
            for sid, spec in specs.items():
                spec_str = _safe_get_str(runtime.id_mapper, "item_spec", sid)
                items.append(InventoryItemResponse(
                    item_spec_id=spec_str,
                    name=spec.name,
                    description=spec.description,
                    quantity=counts[sid],
                ))

        return InventoryResponse(character_id=character_id, items=items)

    # ── Chat (stub) ──

    def send_chat_message(
        self, request: ChatSendRequest
    ) -> ChatMessageResponse:
        if request.scope != "individual":
            raise ValueError("Only individual chat scope is currently supported")

        state = self._sessions.get(request.session_id)
        if state is None:
            raise ValueError(f"Session not found: {request.session_id}")
        if state.runtime is None:
            raise ValueError(f"Session has no active runtime: {request.session_id}")

        runtime = state.runtime

        try:
            target_player_int = runtime.id_mapper.get_int(
                "player", request.target_character_id
            )
        except (ScenarioIdMappingError, KeyError):
            try:
                character_index = state.character_ids.index(request.target_character_id)
                target_player_int = runtime.get_player_ids()[character_index].value
            except (ValueError, IndexError) as exc:
                raise ValueError(
                    f"Character not found in session: {request.target_character_id}"
                ) from exc

        target_player_id = PlayerId(target_player_int)
        now = datetime.now(timezone.utc)
        # 1 tick = 5 分 の旧仮定を廃止。runtime の正規 _time_label に委譲する
        # (day_night サイクルから派生した正しい時刻を返す)。
        tick = runtime.current_tick() if callable(getattr(runtime, "current_tick", None)) else 0
        runtime_label_fn = getattr(runtime, "_time_label", None)
        if callable(runtime_label_fn):
            time_label = runtime_label_fn()
        else:
            hours = tick % 24
            time_label = f"深夜 {hours}:00" if hours < 6 else f"{hours}:00"

        output = ObservationOutput(
            prose=f"どこからか、あなたに向けた声が届いた: 「{request.message}」",
            structured={
                "type": "user_directed_speech",
                "speaker": "user",
                "target_character_id": request.target_character_id,
                "content": request.message,
                "channel": "direct",
            },
            observation_category="social",
            schedules_turn=True,
            breaks_movement=False,
        )

        appender = getattr(state.llm_wiring, "observation_appender", None)
        if appender is None:
            buffer = getattr(runtime, "_obs_buffer", None)
            if buffer is None:
                raise ValueError("Session runtime does not expose an observation buffer")
            appender = ObservationAppender(buffer)
        appender.append(target_player_id, output, now, time_label)

        turn_trigger = getattr(state.llm_wiring, "llm_turn_trigger", None)
        if turn_trigger is not None:
            turn_trigger.schedule_turn(target_player_id)
        else:
            state.pending_llm_turns.add(target_player_id.value)

        message = ChatMessageResponse(
            sender="player",
            message=request.message,
            timestamp=_utcnow_iso(),
            is_player=True,
        )
        key = f"{request.session_id}:{request.target_character_id}"
        # setdefault + append は GIL-atomic でないので、tick thread 側からの
        # 読み出しと competing しないよう lock 内で実行する。
        # ついでに上限超過分を捨てる。
        with self._chat_history_lock:
            for k in (key, request.target_character_id):
                bucket = self._chat_histories.setdefault(k, [])
                bucket.append(message)
                if len(bucket) > self._CHAT_HISTORY_MAX_PER_KEY:
                    # 古い方から削る
                    del bucket[: len(bucket) - self._CHAT_HISTORY_MAX_PER_KEY]
        return message

    def get_chat_history(
        self, character_id: str
    ) -> Optional[ChatHistoryResponse]:
        with self._chat_history_lock:
            return ChatHistoryResponse(
                messages=list(self._chat_histories.get(character_id, []))
            )

    # ── Results (stub) ──

    def get_result_impressions(
        self, session_id: str
    ) -> Optional[ResultImpressionResponse]:
        return None

    def get_result_timeline(
        self, session_id: str
    ) -> Optional[ResultTimelineResponse]:
        return None

    def get_result_relationships(
        self, session_id: str
    ) -> Optional[ResultRelationshipResponse]:
        return None

    # ── Saves (stub) ──

    def list_saves(self) -> SaveListResponse:
        return SaveListResponse()

    def save_session(self, session_id: str) -> Optional[SaveSlotResponse]:
        return None

    def load_save(self, save_id: str) -> Optional[SaveSlotResponse]:
        return None
