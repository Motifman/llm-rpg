"""Central manager that bridges FastAPI routers with the game runtime.

Wires ``WorldRuntime`` / scenario loaders / session lifecycle to
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
    is_reschedulable_error_code,
)
from ai_rpg_world.application.llm.services.tool_executor_helpers import (
    with_inner_thought_empty_warning,
)
from ai_rpg_world.application.llm.services.subjective_args import (
    extract_subjective_action_fields,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    format_action_summary_for_display,
)
from ai_rpg_world.application.llm.services.memo_completion_hint_service import (
    MemoCompletionHintService,
)
from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
    ToolCallLoopGuardService,
)
from ai_rpg_world.application.llm.services.world_llm_prompt import (
    CharacterPromptInput,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_MEMORY_RECALL_BY_HANDLE,
    TOOL_NAME_MEMORY_RECALL_EPISODES,
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
# PR-θ3 (経路統合): 旧 _handle_interact 削除に伴い
# InteractionNotAllowedException / InteractionNotFoundException / SpotObjectId
# の import は不要になった (SpotGraphToolExecutor._interact に移動)。
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


def _character_to_prompt_input(
    character: Optional[CharacterDetailResponse],
) -> Optional[CharacterPromptInput]:
    if character is None:
        return None
    return CharacterPromptInput(
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


# PR-J: LLM tool 名 typo の救済ヘルパ。
#
# 単純な ``difflib.get_close_matches`` は ``spot_graph_*`` のように長い共通
# prefix を持つ tool 群で false positive が出る (例: ``spot_graph_gather`` →
# ``spot_graph_wait`` が ratio 0.81 で match してしまう)。
#
# 代わりに **"prefix segment 一致 + suffix 比較"** を使う:
#   1. ``_`` 区切りの単語列にする
#   2. ``requested`` と各 candidate で先頭から一致する segment 数を数える
#   3. 1 segment 以上一致した candidate のみ残し、その suffix (= 残り部分)
#      同士で fuzzy match する
#
# これにより:
# - ``speech_speech`` → ``speech_speak`` (= 同 prefix で suffix 類似)  ✅
# - ``spot_graph_pickup`` → ``spot_graph_pickup_item`` (= 短縮形)       ✅
# - ``spot_graph_gather`` / ``spot_graph_harvest`` → None (想像由来は救わない) ✅
# - ``say`` → None (= 共通 prefix segment 0)                           ✅
_SUFFIX_RATIO_CUTOFF: float = 0.5
_SHORTENED_NAME_SCORE: float = 0.95

# PR-CC (Y_after_pr639_640 後続): 旧 ``spot_graph_`` prefix を廃止した後も、
# LLM は数 tick / 数 turn の間は「習慣」で ``spot_graph_pickup`` のような旧
# prefix 付き名を投げてくる可能性が高い。fuzzy match は「共通 prefix segment
# が 1 つ以上」を要求するため、旧 prefix 付き入力は valid (= bare 名) に対して
# 一切マッチしない。この差を吸収するため、requested の先頭が旧 prefix なら
# 剥がしたバージョンでも比較を試みる。
_LEGACY_TOOL_PREFIXES: tuple[str, ...] = ("spot_graph_",)


def suggest_closest_tool_name(
    requested: str, valid_tools: Iterable[str]
) -> Optional[str]:
    """typo っぽい tool 名から、最も近い valid tool 名 1 件を返す。

    共通 prefix segment が 1 つも無い候補は除外し、残った候補のうち suffix の
    類似度 (cutoff = ``_SUFFIX_RATIO_CUTOFF`` = 0.5) が最も高いものを返す。
    短縮形 (= requested の suffix が空) は ``_SHORTENED_NAME_SCORE`` 固定で
    常に救う。

    cutoff 0.5 は ``speech_speech → speech_speak`` の suffix 比較 ratio が
    0.545 になる事実から決定した境界値。これ未満にすると想像由来 typo
    (= ``gather`` / ``harvest``) の false positive が増える。

    候補が無ければ ``None``。「想像由来」(= ``gather`` / ``harvest`` のような
    独立した語) は本関数では救わず、``valid_tools`` 一覧の併記で agent に
    再選択させる設計。
    """
    from difflib import SequenceMatcher

    if not isinstance(requested, str) or not requested:
        return None
    valid_list = [v for v in valid_tools if isinstance(v, str) and v]
    if not valid_list:
        return None

    # PR-CC 追加: 旧 prefix 剥がしを試す (bare 名との fuzzy 比較を可能にする)。
    # 「spot_graph_pickup → pickup_item」のような救済経路。
    # 元の requested と剥がした版の両方を候補にして、スコアが高い方を選ぶ。
    candidates_to_try: list[str] = [requested]
    for legacy in _LEGACY_TOOL_PREFIXES:
        if requested.startswith(legacy) and len(requested) > len(legacy):
            candidates_to_try.append(requested[len(legacy):])
            break

    best: Optional[str] = None
    best_score: float = 0.0
    for req_variant in candidates_to_try:
        variant_best, variant_score = _fuzzy_score_variant(req_variant, valid_list, SequenceMatcher)
        if variant_score > best_score:
            best_score = variant_score
            best = variant_best

    # strict `>` を使う: `harvest` vs `travel_to` が ratio=0.5 で false positive
    # にならないように、cutoff と等しい match は救わない。`speech_speak`
    # (= ratio 0.545) は通る。
    if best_score > _SUFFIX_RATIO_CUTOFF:
        return best
    return None


def _fuzzy_score_variant(
    requested: str, valid_list: list[str], SequenceMatcher
) -> tuple[Optional[str], float]:
    """1 つの ``requested`` variant について、valid 側から最高スコアを持つ
    候補を返す。``suggest_closest_tool_name`` の内部ヘルパー。"""
    req_parts = requested.split("_")
    best: Optional[str] = None
    best_score: float = 0.0
    for cand in valid_list:
        cand_parts = cand.split("_")
        common = 0
        for r, c in zip(req_parts, cand_parts):
            if r == c:
                common += 1
            else:
                break
        if common == 0:
            continue  # 全く異なるカテゴリ
        req_suffix = "_".join(req_parts[common:])
        cand_suffix = "_".join(cand_parts[common:])
        if not req_suffix and cand_suffix:
            # 短縮形 (e.g. spot_graph_pickup → spot_graph_pickup_item)
            score = _SHORTENED_NAME_SCORE
        elif not cand_suffix and req_suffix:
            # 逆短縮 (= candidate がより短い)。これは LLM が「サフィックス付
            # きの方を呼びたかった」と推定するには弱いので 0.0 扱い
            score = 0.0
        elif not req_suffix and not cand_suffix:
            # 完全一致 (= requested == cand。この経路は handler が見つかって
            # いるはずなので来ない、念のため)
            score = 1.0
        else:
            score = SequenceMatcher(None, req_suffix, cand_suffix).ratio()
        if score > best_score:
            best_score = score
            best = cand
    return best, best_score


def build_unsupported_tool_message(
    *, requested: str, valid_tools: Iterable[str]
) -> str:
    """UNSUPPORTED_TOOL 用のエラーメッセージを組み立てる。

    含む情報:
    1. typoed name (= LLM が何を呼ぼうとしたか)
    2. fuzzy suggestion (= 「もしかして 'X' ですか?」、近い候補がある時のみ)
    3. valid tool 一覧 (= 想像由来 typo を救うため常時併記)
    """
    valid_sorted = sorted(v for v in valid_tools if isinstance(v, str) and v)
    suggestion = suggest_closest_tool_name(requested, valid_sorted)

    head = f"未対応のツールです: {requested}"
    if suggestion:
        head += f"。もしかして '{suggestion}' ですか?"
    else:
        head += "。"
    tail = f" 現在使える tool: [{', '.join(valid_sorted)}]"
    return head + tail


class ToolHandlerConsistencyError(RuntimeError):
    """tool spec が expose する tool 名集合と、_tool_handlers の dispatch SSOT
    キー集合の間に欠落があるときに投げられる。

    過去 PR #589 / #590 で「LLM に tool spec を見せているのに dispatch 側に
    handler が無く UNSUPPORTED_TOOL に化ける」silent failure が発生したため、
    本例外で起動時に fail-fast させる。"""


# PR-A (Issue #621 後続): 脱出ランタイムでは恒久的に未対応な tool。
# ``_handle_set_sub_location`` が常に ``UNSUPPORTED_TOOL`` を返すため LLM に
# 見せる意味が無い。Y_after_issue621 trace で実際に 3 回叩かれて全部失敗した
# ので、tools_payload の構築時にここで定義された名前を弾く。handler 自体は
# 防御として残し、何らかの経路で呼ばれても安全に UNSUPPORTED_TOOL を返す。
#
# 別ランタイム (= 通常 SpotGraph) で set_sub_location が必要になった場合は
# このフィルタを呼ばないことで通せる (= ToolDefinitionDto 側に変更不要)。
ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS: frozenset[str] = frozenset({
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
})


def filter_definitions_for_escape_llm(definitions):
    """``ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS`` に含まれる tool definition を除外する。

    入力順を保ったまま、name 属性が除外対象に該当するものだけを取り除く。
    """
    return [d for d in definitions if d.name not in ESCAPE_RUNTIME_LLM_EXCLUDED_TOOLS]


def validate_tool_handler_consistency(
    exposed_tool_names: Iterable[str],
    handler_keys: Iterable[str],
) -> None:
    """tool spec の集合が dispatch handler の集合に含まれていることを保証する。

    spec に出ているのに handler が無い tool を見つけたら
    ``ToolHandlerConsistencyError`` を投げる。handler だけ存在し spec に居ない
    ケース (= feature flag OFF や aux executor 常駐) は許容する。
    """
    exposed = set(exposed_tool_names)
    registered = set(handler_keys)
    missing = exposed - registered
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ToolHandlerConsistencyError(
            "Tool spec exposes tools without dispatch handlers: "
            f"[{missing_list}]. "
            "_tool_handlers (= dispatch SSOT) にエントリを追加してください。"
        )


@dataclass
class _WorldSpawnAllPlayersLlmResolver(ILLMPlayerResolver):
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


# PR-θ3 (経路統合): 旧 module-level 関数 `_interact_remediation_for_reason` /
# `_list_object_interactions` / `_INTERACTION_EXHAUST_HINTS` は application 層
# (application/llm/services/executors/interact_helpers.py) に移動した。
# 参照は SpotGraphToolExecutor._interact が持ち、旧 handler は削除された。


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


# #346 Step 3 / #404: per-agent idle timer の沈黙上限。`note_player_activity`
# 以降 N tick 何も起きなければ heartbeat 1 件で起こす。デフォルト 6 tick
# (旧固定値 5 から +1 で安全寄り)。env で実験ごとに上げて沈黙許容を強める / 下げて
# 古い挙動に戻すなど調整できる。
_LLM_IDLE_TIMEOUT_TICKS_ENV = "LLM_IDLE_TIMEOUT_TICKS"
_LLM_IDLE_TIMEOUT_TICKS_DEFAULT = 6


def _resolve_llm_idle_timeout_ticks(
    default: int = _LLM_IDLE_TIMEOUT_TICKS_DEFAULT,
) -> int:
    """env から idle timeout (= heartbeat interval) を読む。

    不正値 / 1 未満は default に戻す。**設定上限は設けない** (運用で「丸 1 日
    沈黙を許す」のような長期 idle も自由に試せるように)。
    """
    raw = os.environ.get(_LLM_IDLE_TIMEOUT_TICKS_ENV)
    if raw is None:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    return max(1, n)


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
        tool_names: Optional[list[str]] = None,
    ) -> None:
        self._trace_recorder = trace_recorder
        self._runtime = runtime
        self._player_id_value = int(player_id.value)
        # PR-F: LLM がその tick の prompt で実際に見たツール名集合。trace に
        # 残すことで「tend_to_player が本当に prompt に流れたか」「tool catalog
        # の wiring が壊れていないか」「prompt の tool 集合が tick ごとに
        # 安定しているか (= cache key 安定性)」が後から検証できる。
        # 未指定 (= 既存 caller) は空 list として記録する (= 「明示的に
        # 渡さなかった」を「不在」と区別しないシンプル運用)。
        self._tool_names: list[str] = list(tool_names) if tool_names else []

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
                # OpenRouter 経由のとき usage.cost (USD) が乗る。直結 / vLLM では 0.0。
                # 実験 trace を見れば cost 合計が事後計算できる。
                cost_usd=getattr(metrics, "cost_usd", 0.0),
                # PR-F: LLM 視点での「見えていた tool 一覧」。
                tool_names=list(self._tool_names),
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
class _WorldLlmTurnTrigger:
    """Queues LLM turns and runs them against the session runtime.

    ## 「turn」「ターン」という言葉について

    本クラスの ``run_scheduled_turns`` / ``schedule_turn`` の "turn" は
    **TRPG の順番待ち** の意味では **無い**。実体は event 駆動の wave
    実行: 1 world tick = 1 wave、 wave 内で ``pending_player_ids`` の
    全員を並列に LLM 呼び出しする。

    ## ``_self_reschedule_streak`` の責務 (= 旧名 ``_turn_counts``)

    **「自分の ``result.should_reschedule=True`` で繰り返し起床する
    self-loop チェイン」の連続数を ``max_self_reschedule_streak`` で
    打ち切る** ためのカウンタ。**他者観測 / 失敗通知 / arrival callback
    等の外部起床 (= schedule_turn 経由) は streak を触らない** ので、
    ping-pong (= A↔B が互いに発話で起こし合う相互作用) は無限に許容する
    (= 自然な振る舞いなので止めない)。

    chain を終了させる条件:
    - ``was_no_op=True`` (= LLM が tool を返さなかった)
    - ``should_reschedule=False`` (= 通常成功 or reschedule 不要な失敗)
    - streak が ``max_self_reschedule_streak`` に到達 (= self-loop の強制 stop)

    旧名 ``max_turns`` / ``_turn_counts`` は「TRPG ターン上限」を連想させて
    誤読を招いていたため、PR-I で意味を反映した名前に変更した。

    ## PR-I の挙動変化 (意図的)

    1. ``schedule_turn`` が ``_self_reschedule_streak`` を一切触らない
       (旧: ``setdefault(pid, 0)`` で「未登録なら 0 を入れる」をしていたが、
       外部起床経路は self-loop chain と独立であるべきという原則に合わせて
       撤廃)
    2. 旧 ``_account_result`` の ``elif should_reschedule or current_count < max_turns``
       が含意していた「**should_reschedule に関わらず max ターンまで auto-stay**」
       挙動を撤廃。新コードは ``should_reschedule=True`` の時だけ streak を
       積んで pending に再追加する。``should_reschedule=False`` (= 通常成功 or
       reschedule 不要な失敗) は即 chain 終了 = streak pop。

    ## 1. の影響範囲

    ``schedule_turn`` は他者観測 / arrival callback / idle timer が呼ぶ経路で、
    self-loop chain (= 同一 agent 自走) とは独立。streak を触らないことで
    ping-pong (= A↔B の発話で起こし合う相互作用) が永続的に成立する。

    ## 2. の影響範囲

    調査済み: ``should_reschedule=True`` を実際に返す経路は
    ``_RESCHEDULE_ERROR_CODES`` (= ``NO_TOOL_CALL`` / ``LLM_API_CALL_FAILED`` /
    ``LLM_RATE_LIMIT`` / ``INVALID_DESTINATION_LABEL``) に該当する失敗のみ。
    通常成功は ``should_reschedule=False`` がデフォルト。よって「auto-stay 5
    turns に暗黙的に依存するコード」は事実上存在せず、本変更は実走の挙動を
    変えない。Y 実走で観測された「**player 1 が 75 wave 連続活動**」は
    auto-stay の副産物ではなく **外部観測連鎖**による正当な活動だったので、
    新コードでも同じパターンが再現する。
    """

    wiring: "_WorldLlmWiring"
    # 自己 reschedule チェインの連続上限。これに達したら pending から外す。
    # 他者観測経由の起床は影響を受けないので、ping-pong は影響なし。
    max_self_reschedule_streak: int = 5
    pending_player_ids: set[int] = field(default_factory=set)
    # 旧名 _turn_counts。pid → 自己 reschedule の連続回数。
    _self_reschedule_streak: dict[int, int] = field(default_factory=dict)

    def schedule_turn(self, player_id: PlayerId) -> None:
        """外部要因 (他者観測 / arrival / idle timer 等) による起床。

        **``_self_reschedule_streak`` には触らない**。これにより:
        - ping-pong (= 他者発話で起こし合う) は streak を 0 リセットせず、
          かつ streak を増やしもしないので、永続的に成立する
        - self-loop の streak (= 既に積まれていた値) も保持される。次の
          turn で should_reschedule=True なら +1 して累積する
        - pop 済 pid に対しては未登録扱い、次の self-reschedule で 1 から
          数え直す (= ``_self_reschedule_streak.get(pid, 0)`` の default 経由)
        """
        self.pending_player_ids.add(player_id.value)

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
                    self._self_reschedule_streak.clear()
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
        """turn 完了後の self-reschedule streak 管理を 1 か所に集約する。

        chain を終わらせる条件:
        - ``result.was_no_op``: LLM が tool を返さなかった (= chain 中断)
        - ``result.should_reschedule=False``: 通常成功 or reschedule 不要な
          失敗 (= self-loop ではない)
        - streak が ``max_self_reschedule_streak`` に到達: self-loop の
          強制 stop

        chain を継続する条件:
        - ``result.should_reschedule=True`` かつ streak が未到達 → streak +1
          して pending に再追加
        """
        current_streak = self._self_reschedule_streak.get(player_id_value, 0) + 1
        if result.was_no_op:
            # tool を返さなかった = chain 中断
            self._self_reschedule_streak.pop(player_id_value, None)
        elif not result.should_reschedule:
            # 通常成功 or reschedule 不要な失敗 = chain 終了
            self._self_reschedule_streak.pop(player_id_value, None)
        elif current_streak >= self.max_self_reschedule_streak:
            # 上限到達: chain を強制終了して streak を pop (= 次回 fresh start)。
            # **pending には触らない**: 同 wave で他者観測経由で
            # schedule_turn された外部起床を消さないため。
            # 結果として:
            #   - 同 wave で外部観測があれば次 wave で走る (= 外部起床は妨げない)
            #   - 外部観測が無ければ次 wave で走らない (= 自走 chain は止まる)
            #   - 次回 should_reschedule=True を返した時は streak=1 からの新しい
            #     chain として数え直す (= soft cap)
            self._self_reschedule_streak.pop(player_id_value, None)
        else:
            # should_reschedule=True かつ未到達 → streak を累積して chain 継続
            self._self_reschedule_streak[player_id_value] = current_streak
            self.pending_player_ids.add(player_id_value)
        # #346 Step 3 / #404: per-agent idle timer の last 更新。turn が走った
        # = 「いま活動した」なので heartbeat の沈黙タイマーをリセットする。
        # event 駆動で頻繁に動く player には heartbeat が出なくなり、
        # 完全 idle な player だけ idle_timeout 経過後に 1 回起こされる。
        self._note_activity_after_turn(player_id_value)
        # #526 / U3: 段1 エピソード再解釈の trigger 後半。turn 完了を coordinator に
        # 通知し、interval 到達時に pending recall batch を LLM 再解釈する。
        # reinterpretation OFF (coordinator 未構築) では no-op。
        self._note_turn_for_reinterpretation(player_id_value)
        # PR-T: 次回 prompt の「身体の状態」差分表示用に need 値を snapshot する。
        # 「前回の自分のターン終了時 → 次回 prompt」までの変化が delta として
        # 表示される (= 自然 decay + 他者観測の影響 + own action 結果)。
        self._snapshot_needs_after_turn(player_id_value)

    def _snapshot_needs_after_turn(self, player_id_value: int) -> None:
        """PR-T: turn 終了時に当該 player の現在 need 値を「前回」として保存する
        fail-safe ヘルパ。次回 turn の prompt build で diff 表示に使われる。
        """
        runtime = self.wiring.runtime
        repo = getattr(runtime, "_player_status_repo", None)
        if repo is None:
            return
        try:
            player_status = repo.find_by_id(PlayerId(player_id_value))
            if player_status is not None and hasattr(
                player_status, "snapshot_needs_for_delta"
            ):
                player_status.snapshot_needs_for_delta()
                repo.save(player_status)
        except Exception:
            # snapshot 精度低下は致命ではない (差分が 0 になるだけ)
            logger.warning(
                "snapshot_needs_for_delta failed for player_id=%s",
                player_id_value,
                exc_info=True,
            )

    def _note_turn_for_reinterpretation(self, player_id_value: int) -> None:
        """reinterpretation coordinator に turn 完了を通知する fail-safe ヘルパ。

        coordinator 未配線 (reinterpretation OFF) / 異常系では何もしない
        (turn 実行自体は壊さない)。``_note_activity_after_turn`` と同じ方式。
        """
        stack = getattr(self.wiring.runtime, "_episodic_stack", None)
        coordinator = (
            getattr(stack, "reinterpretation_coordinator", None) if stack else None
        )
        if coordinator is None:
            return
        try:
            coordinator.after_turn_completed(PlayerId(player_id_value))
        except Exception:
            # 再解釈の失敗は致命ではない (worst case: 再解釈が進まないだけ)。
            logger.warning(
                "reinterpretation after_turn_completed failed for player=%s",
                player_id_value,
                exc_info=True,
            )

    def _note_activity_after_turn(self, player_id_value: int) -> None:
        """heartbeat emitter に「player が今ターン走った」を通知する fail-safe ヘルパ。

        emitter 未配線 / 異常系では何もしない (turn 実行自体は壊さない)。
        """
        runtime = self.wiring.runtime
        emitter = None
        sim = getattr(runtime, "_simulation_service", None)
        if sim is not None:
            emitter = getattr(sim, "_heartbeat_emitter", None)
        if emitter is None or not hasattr(emitter, "note_player_activity"):
            return
        try:
            from ai_rpg_world.domain.common.value_object import WorldTick
            current = int(runtime.current_tick())
            emitter.note_player_activity(
                PlayerId(player_id_value), WorldTick(current)
            )
        except Exception:
            # idle timer の精度低下は致命ではない (worst case 旧来挙動)
            logger.warning(
                "note_player_activity failed for player_id=%s",
                player_id_value,
                exc_info=True,
            )

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
class _WorldLlmWiring:
    """Session-local LLM loop for the world runtime.

    **Two-phase construction invariant**:
    ``action_failed_emitter`` と ``intent_id_generator`` は ``ObservationTurnScheduler``
    → ``ActionFailedObservationEmitter`` の構築連鎖が ``llm_turn_trigger`` を
    必要とするため、本クラスの ``__init__`` 直後に注入する必要がある。
    ``create_session`` の流れは:

        1. ``_WorldLlmWiring(...)`` を ctor で作成 (内部で trigger 生成)
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
    # 旧名 max_turns。trigger に passthrough する。意味は「自己 reschedule
    # チェインの連続上限」(= TRPG のターン数ではない)。詳細は
    # ``_WorldLlmTurnTrigger`` の docstring を参照。
    max_self_reschedule_streak: int = 5
    # 失敗 DTO を ActionFailed 観測に変換する emitter (Optional)。
    # ``attach_action_failed_wiring`` で配線される。None の場合は失敗観測を
    # 発行しない (後方互換 / テスト用ショートカット)。
    action_failed_emitter: Optional[ActionFailedObservationEmitter] = None
    # ActionFailed 観測の intent.intent_id を払い出すカウンタ。
    # action_failed_emitter とセットで使う想定。
    intent_id_generator: Optional[IntentIdGenerator] = None

    def __post_init__(self) -> None:
        self.observation_appender = ObservationAppender(self.observation_buffer)
        self.llm_turn_trigger = _WorldLlmTurnTrigger(
            wiring=self,
            max_self_reschedule_streak=self.max_self_reschedule_streak,
        )
        # PR 4 (#227): 同一ツール連打を engine 側で検知し、警告を観測として
        # 注入する loop guard。PR #230 で LlmAgentOrchestrator 経由で配線
        # していたが、world_runtime の独自 turn 実行はそれを経由しないため、
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
        # 同じ instance を prompt_builder にも共有させる。record_and_check で
        # 進めた streak を peek_streak で読んで、instruction 末尾に「同じ手
        # 連続中」warning prefix を載せる。 recent_events に並ぶ既存の警告は
        # 埋もれやすいので、recency bias が効く instruction 直前にも同じ意図
        # の prompt を流して二重に attention を取りに行く。
        if hasattr(self.runtime, "set_tool_call_loop_guard"):
            self.runtime.set_tool_call_loop_guard(self.tool_call_loop_guard)
        # PR 5 (#227): memo 完了 hint。LLM が memo_done を呼ばずに memo を
        # 放置するケースを救済するため、action_summary / result_summary と
        # 未完了 memo の content を SequenceMatcher で比較し、類似度が高ければ
        # 「memo を完了したかも」hint を result.message に append する。
        # PR #230 で本家経路に配線済みだが、world_runtime の独自 turn 実行は
        # 経由しないため、ここで wiring に直接組み込む。
        # Phase 3 Step 3a-3: MemoCompletionHintService に Resolver/WorldId を
        # 注入する。world_runtime の auxiliary tool stack 経由で provision された
        # Being を参照できるよう、runtime の aux_being_resolver property を利用する。
        memo_store = getattr(self.runtime, "_todo_store", None)
        # runtime 側で aux being stack を初期化しておく (= property が None で
        # ない状態にする)。idempotent な呼び出し。
        if memo_store is not None and hasattr(
            self.runtime, "_wire_auxiliary_tool_stack"
        ):
            try:
                self.runtime._wire_auxiliary_tool_stack()
            except Exception:
                logger.warning(
                    "_wire_auxiliary_tool_stack failed; "
                    "MemoCompletionHintService will be disabled",
                    exc_info=True,
                )
        aux_resolver = getattr(self.runtime, "aux_being_resolver", None)
        aux_world_id = getattr(self.runtime, "aux_being_default_world_id", None)
        if memo_store is not None and aux_resolver is not None and aux_world_id is not None:
            self.memo_completion_hint_service: Optional[MemoCompletionHintService] = (
                MemoCompletionHintService(
                    memo_store=memo_store,
                    being_attachment_resolver=aux_resolver,
                    default_world_id=aux_world_id,
                )
            )
        else:
            self.memo_completion_hint_service = None
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
            # PR-θ1/θ2/θ3/θ4 (経路統合): TRAVEL_TO / EXPLORE / INTERACT /
            # LISTEN の登録は削除した。代わりに _wire_missing_spot_graph_tools
            # が SpotGraphToolExecutor._travel_to / _explore / _interact /
            # _listen を上書き wire する。旧 handlers は削除された。
            TOOL_NAME_SPOT_GRAPH_WAIT: self._handle_wait,
            TOOL_NAME_SPEECH: self._handle_speech,
            TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION: self._handle_set_sub_location,
            TOOL_NAME_TODO_ADD: self._make_auxiliary_tool_handler(TOOL_NAME_TODO_ADD),
            TOOL_NAME_TODO_LIST: self._make_auxiliary_tool_handler(TOOL_NAME_TODO_LIST),
            TOOL_NAME_TODO_COMPLETE: self._make_auxiliary_tool_handler(
                TOOL_NAME_TODO_COMPLETE
            ),
            # Issue #526 後続: memory_recall_episodes も aux 経路で dispatch する。
            # ``runtime.run_llm_auxiliary_tool`` が ``_memory_recall_tool_executor``
            # を併用するよう PR #535 で配線済み。tool 定義は episodic_stack ON
            # のときだけ ``get_tool_definitions`` で expose される。
            TOOL_NAME_MEMORY_RECALL_EPISODES: self._make_auxiliary_tool_handler(
                TOOL_NAME_MEMORY_RECALL_EPISODES
            ),
            # PR-D (#588) 後続 fix: memory_recall_by_handle も同じ aux 経路に
            # 載せる。SSOT である本テーブルにエントリが無いと
            # ``execute_tool`` の dispatcher が UNSUPPORTED_TOOL を返す silent
            # failure になる (= Run D で 30 tick 中 2 回呼ばれたが両方失敗した
            # 直接原因)。tool 定義は afterglow_store + slot_store が揃った
            # ときだけ ``get_tool_definitions`` で expose されるので、ここに
            # 居ても afterglow off の run では一切呼ばれない (= 安全)。
            TOOL_NAME_MEMORY_RECALL_BY_HANDLE: self._make_auxiliary_tool_handler(
                TOOL_NAME_MEMORY_RECALL_BY_HANDLE
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
                # PR-θ1 (経路統合) レビュー HIGH #2: travel_to は本来
                # runtime.do_move + runtime.id_mapper + runtime._spot_graph_repo
                # しか要らないが、経路統合で他 tool と同じ needed check の下に
                # 組み込まれた。従って interaction_service / exploration_service
                # 等が欠けた test wiring では travel_to まで UNSUPPORTED_TOOL に
                # 化ける。production wiring (world_runtime.py) では needed が
                # 必ず全部揃うので顕在化しないが、将来的な軽量 wiring / mock
                # 構成で travel_to だけが理由不明に消える silent failure リスク
                # がある。travel_to 独立 wire は経路が再び分裂するので却下、
                # 本コメントで risk を明示するに留める。
                logger.warning(
                    "_wire_missing_spot_graph_tools: runtime is missing %s; "
                    "use_item / attack / give_item / pickup_item / drop_item / "
                    "prepare_action / tend_to_player / travel_to will remain "
                    "UNSUPPORTED_TOOL.",
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
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
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
            # 実験 #29 後続: travel/give/drop/pickup の say_inline 短発話用。
            speech_service=getattr(runtime, "_speech_service", None),
            # PR-θ1 (経路統合): travel_to を旧 _handle_travel_to から新経路
            # SpotGraphToolExecutor._travel_to に統合するため runtime を注入。
            # _travel_to 内部で runtime.do_move を呼んで単一の副作用実装を
            # 共有する。runtime.do_move は既に start_travel_to_spot +
            # _process_graph_events + 同一 spot 短絡 + _record_action_result
            # (scene_boundary + subjective) を面倒見ている。
            runtime=runtime,
        )
        self._spot_graph_executor = executor
        raw_handlers = executor.get_handlers()
        # executor は (player_id_int, args) -> result の signature。
        # _tool_handlers は (PlayerId, args, runtime_context) -> result なので
        # ラップして adapt する。runtime_context は executor 側で使わない。
        # PR-α (Y_after_pr639_640 後続): 旧 give_items は削除、give_item に
        # batch-always で統合された。旧 PR-E のコメントで触れていた
        # 「give_items が漏れる silent failure」問題は本 refactor で不要になった。
        targets = (
            TOOL_NAME_SPOT_GRAPH_USE_ITEM,
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            TOOL_NAME_SPOT_GRAPH_GIVE_ITEM,
            TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
            TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
            TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
            # PR-θ1 (経路統合): travel_to を旧 _handle_travel_to から新経路
            # SpotGraphToolExecutor._travel_to に統合。以前は 2 経路に分裂して
            # おり travel_to の say_inline が 100% silent failure していた。
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            # PR-θ2 (経路統合): explore を旧 _handle_explore から新経路
            # SpotGraphToolExecutor._explore に統合。旧 handler 相当の
            # 「発見なし時に可視 object 併記」も新経路で保持 (runtime_context
            # 経由で targets を参照)。
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            # PR-θ3 (経路統合): interact を旧 _handle_interact から新経路
            # SpotGraphToolExecutor._interact に統合。旧 handler 相当の
            # InteractionNotAllowedException / InteractionNotFoundException
            # ハンドリング (LLM 向け remediation + 利用可能操作列挙) も新経路で
            # 保持。resolver エラー時の invalid_label_failure_builder も設定。
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            # PR-θ4 (経路統合): listen を旧 _handle_listen から新経路
            # SpotGraphToolExecutor._listen に統合。runtime.do_listen 経由で
            # 副作用 (_process_graph_events / event 差分カウント) は保持。
            TOOL_NAME_SPOT_GRAPH_LISTEN,
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
            # attack も resolver 経由で `target_label='大型カニ'` を
            # `monster_id` に解決する必要がある。Issue #618 で発覚した
            # silent failure: resolver に hook されていなかったため、
            # agent が attack を呼ぶと毎回 `INVALID_TARGET_LABEL: monster_id
            # が解決されていません` で reject されていた (= scenario で
            # モンスターと戦えない致命的 bug)。
            TOOL_NAME_SPOT_GRAPH_ATTACK,
            # Issue #621 Phase 3b: 新 tool `tend_to_player`。
            # `target_player_label='エイダ'` を `target_player_id` に解決して
            # executor に渡す必要があるため resolver hook が必須。
            TOOL_NAME_SPOT_GRAPH_TEND_TO_PLAYER,
            # PR-θ1 (経路統合): travel_to も resolver 経由で
            # `destination_label='森の広場'` を `destination_spot_id` に解決
            # する。旧 handler は handler 内で resolve していたが、新経路は
            # resolver stage で SpotGraphArgumentResolver._resolve_travel_to
            # (`resolve_destination_target` 同一関数を再利用) が変換する。
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            # PR-θ3 (経路統合): interact も resolver 経由で
            # `object_label='OBJ1'` を `object_id` に解決する。旧 handler と
            # 同じく resolver 例外時の「有効な object_label 一覧」 message は
            # invalid_label_failure_builder で構築する。
            TOOL_NAME_SPOT_GRAPH_INTERACT,
        })
        argument_resolver = SpotGraphArgumentResolver()
        for tool_name in targets:
            raw = raw_handlers.get(tool_name)
            if raw is None:
                continue
            if tool_name in resolver_targets:
                # PR-θ1/θ3 (経路統合): travel_to / interact は resolver 例外時に
                # 「有効な label 一覧 + should_reschedule」を含む tool-specific
                # 失敗を組み立てる (旧 handler 相当)。他 tool は従来通り generic
                # message で処理。
                tool_specific_builder = (
                    self._build_travel_to_invalid_label_failure
                    if tool_name == TOOL_NAME_SPOT_GRAPH_TRAVEL_TO
                    else self._build_interact_invalid_label_failure
                    if tool_name == TOOL_NAME_SPOT_GRAPH_INTERACT
                    else None
                )
                self._tool_handlers[tool_name] = (
                    self._adapt_executor_handler_with_resolver(
                        raw, tool_name, argument_resolver,
                        invalid_label_failure_builder=tool_specific_builder,
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
        # PR-E: tool spec (= LLM に見せる) と _tool_handlers (= dispatch SSOT) の
        # 不整合は起動時に止める。pre-warm が aux executor を完成させた直後に
        # 一度だけ実行するため、ここに置く。get_tool_definitions に失敗しても
        # それ自体は通常運用で起きるべきでないが、検証ロジックの破綻で実験を
        # 止めるのは過剰なので例外なら警告だけ残す。
        self._validate_tool_handler_consistency()

    def _validate_tool_handler_consistency(self) -> None:
        """runtime が expose する tool 定義集合と _tool_handlers のキー集合が
        矛盾していないか確認する。expose されているのに handler 未登録の tool
        があれば ``ToolHandlerConsistencyError`` を投げて起動を止める。

        過去 PR #589 / #590 で「LLM には tool を見せているのに dispatch 側で
        UNSUPPORTED_TOOL になる」silent failure を 30 tick 走らせてから気付いた
        ことが直接の動機。
        """
        try:
            definitions = self.runtime.get_tool_definitions()
        except Exception:
            logger.warning(
                "_validate_tool_handler_consistency: get_tool_definitions が "
                "失敗したため整合性検証をスキップする",
                exc_info=True,
            )
            return
        # PR-A: LLM に実際に expose する tool 集合と handler 集合を突合する。
        # 脱出ランタイムで永続的に UNSUPPORTED_TOOL になる tool は除外して比較
        # (= 「expose されているのに handler が無い」検出だけは引き続き機能する)。
        definitions = filter_definitions_for_escape_llm(definitions)
        exposed_names = [d.name for d in definitions]
        validate_tool_handler_consistency(
            exposed_tool_names=exposed_names,
            handler_keys=self._tool_handlers.keys(),
        )

    @staticmethod
    def _build_interact_invalid_label_failure(
        runtime_context: Any,
        arguments: Dict[str, Any],
        exc: Exception,
    ) -> LlmCommandResultDto:
        """PR-θ3 (経路統合): interact の resolver 例外を旧 _handle_interact
        相当の tool-specific 失敗 dto に変換する。

        旧 handler は resolver 例外時に「有効な object_label 一覧を含む
        message + object_label 用の remediation」を組み立てていた。
        """
        targets = getattr(runtime_context, "targets", {}) or {}
        label = str(arguments.get("object_label", ""))
        valid_objects = _list_object_labels(targets)
        error_code = getattr(exc, "error_code", "INVALID_TARGET_LABEL")
        return LlmCommandResultDto(
            success=False,
            message=(
                f"オブジェクトラベルが見つかりません: {label}。"
                f"有効な object_label: "
                f"{valid_objects or '(この場所に interactable なオブジェクトなし)'}"
            ),
            error_code=error_code,
            remediation=(
                "object_label には現在の状況に表示された OBJ1, OBJ2 等の "
                "ラベル (display name ではなく) を指定してください。"
            ),
            should_reschedule=is_reschedulable_error_code(error_code),
        )

    @staticmethod
    def _build_travel_to_invalid_label_failure(
        runtime_context: Any,
        arguments: Dict[str, Any],
        exc: Exception,
    ) -> LlmCommandResultDto:
        """PR-θ1 (経路統合): travel_to の resolver 例外を旧 _handle_travel_to
        相当の tool-specific 失敗 dto に変換する。

        旧 handler は resolver 例外時に:
        1. 有効な destination_label 一覧 (S1, S2, ...) を含む message
        2. destination_label 用の remediation
        3. INVALID_DESTINATION_LABEL 用の reschedule policy を尊重

        の 3 点をやっていた。新経路の resolver adapter は generic message を
        返すため、これらを再現するために tool-specific builder を用意する。
        """
        targets = getattr(runtime_context, "targets", {}) or {}
        label = str(arguments.get("destination_label", ""))
        valid_destinations = _list_destination_labels(targets)
        error_code = getattr(exc, "error_code", "INVALID_DESTINATION_LABEL")
        return LlmCommandResultDto(
            success=False,
            message=(
                f"移動先が見つかりません: {label}。"
                f"有効な destination_label: "
                f"{valid_destinations or '(この場所からの移動先なし)'}"
            ),
            error_code=error_code,
            remediation=(
                "destination_label には現在の状況に表示された S1, S2 等の "
                "ラベル、またはスポット名 (例: 閲覧室) を指定してください。"
            ),
            should_reschedule=is_reschedulable_error_code(error_code),
        )

    @staticmethod
    def _adapt_executor_handler(
        raw_handler: Callable[..., LlmCommandResultDto],
    ) -> Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]:
        """executor signature (int, args[, runtime_context]) → wiring signature
        (PlayerId, args, ctx)。

        PR-θ2 (経路統合): executor が runtime_context を必要とする tool (explore
        の可視 object 併記など、旧 handler が targets を参照していたもの) に
        対応するため、raw_handler 呼び出し時に位置引数として runtime_context
        を渡すよう拡張した。executor 側では第3引数を optional (default None)
        で受ければ、runtime_context を使わない handler は従来と同じシグネチャ
        で動く。
        """
        def _handler(
            player_id: PlayerId,
            arguments: Dict[str, Any],
            runtime_context: Any,
        ) -> LlmCommandResultDto:
            return raw_handler(int(player_id.value), arguments, runtime_context)
        return _handler

    @staticmethod
    def _adapt_executor_handler_with_resolver(
        raw_handler: Callable[[int, Dict[str, Any]], LlmCommandResultDto],
        tool_name: str,
        argument_resolver: Any,
        *,
        # PR-θ1 (経路統合): travel_to の resolver エラー時に旧 handler と同じ
        # 「有効な destination_label 一覧を含む」 message を組み立てるための
        # optional builder。渡されない場合は従来通り generic message を使う。
        # 他 tool (interact / attack 等) 統合時も同じ pattern を再利用できる。
        invalid_label_failure_builder: Optional[
            Callable[[Any, Dict[str, Any], Exception], LlmCommandResultDto]
        ] = None,
    ) -> Callable[[PlayerId, Dict[str, Any], Any], LlmCommandResultDto]:
        """resolver を噛ませた adapter (#356 fix)。

        LLM が送ってくる ``item_label`` (I1/I2) を、executor が読む
        ``item_spec_id`` / ``slot_id`` / ``item_instance_id`` に変換する。
        resolver が例外 (label 見つからない 等) を投げたら ``LlmCommandResultDto``
        に変換して返す (= LLM に「このラベルは存在しない」と surface する)。

        PR-θ1: ``invalid_label_failure_builder`` が渡された場合、resolver 例外
        時にそちらを呼び出して tool-specific な失敗 dto を作れる (旧
        ``_handle_travel_to`` が「有効候補列挙 + should_reschedule」を組み立て
        ていた挙動を新経路でも再現するための拡張点)。
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
                if invalid_label_failure_builder is not None:
                    return invalid_label_failure_builder(
                        runtime_context, arguments, e,
                    )
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
            return raw_handler(int(player_id.value), resolved, runtime_context)

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
        `_WorldLlmTurnTrigger.run_scheduled_turns` 側で行う。
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
        # PR-A: 脱出ランタイムで恒久的に UNSUPPORTED_TOOL になる tool は LLM に
        # 見せない。Y_after_issue621 trace で set_sub_location が 3 回叩かれて
        # 全部失敗していた問題を入口で塞ぐ。
        tools_payload = [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in filter_definitions_for_escape_llm(
                self.runtime.get_tool_definitions()
            )
        ]
        # 実験 #356 対応: LLM 1 呼び出しごとに metrics (wall_latency / tokens / TPS)
        # を trace に流す。Phase A の中で player_id / tick の context を sink に閉
        # じ込めて、後で集計スクリプトが per-agent / per-model 分布を出せるよう
        # にする。
        # PR-F: LLM がその tick で実際に prompt 経由で見た tool 名集合も渡す。
        # tools_payload から function name を抽出する (= OpenAI function calling
        # 形式の "type":"function" 構造から function.name を読む)。
        tool_names = [
            t.get("function", {}).get("name")
            for t in tools_payload
            if t.get("function", {}).get("name")
        ]
        metrics_sink = self._build_llm_metrics_sink(player_id, tool_names=tool_names)
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
        # 注入されていれば記録。LlmAgentOrchestrator 経路を通らない world_runtime
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
                # #552 PR-A: memo hint は target/action/result に key すべきで、
                # 主観入力に依存させない。sanitized summary を使う (健全化)。
                action_summary = format_action_summary_for_display(name, arguments)
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
            # #552 PR-A: raw args の json.dumps をやめ、主観ノイズを落とした
            # sanitized summary を記録する (失敗 / wait / listen 等の経路)。
            # sanitizer が JSON から expected_result を落とすので、構造化フィールドに
            # 予測を残さないと失敗行の [予測:] が消える。subjective を明示的に渡す
            # (成功 core action は do_* 経路で配線済 = U2、ここは generic 経路の補完)。
            self.runtime._record_action_result(
                player_id,
                format_action_summary_for_display(name, arguments),
                result.message,
                tool_name=name,
                success=result.success,
                error_code=result.error_code,
                **extract_subjective_action_fields(arguments),
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
                # PR-AA (Y_after_pr639_640 後続): success / error_code を渡して
                # 「離れた tick に散らばる同一失敗の反復」も検出できるように
                # する。既存の連続 streak 検出とは独立に動作。
                self.tool_call_loop_guard.record_and_check(
                    player_id,
                    name,
                    arguments,
                    success=result.success,
                    error_code=result.error_code,
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
        self, player_id: PlayerId, tool_names: Optional[list[str]] = None,
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
            tool_names=tool_names,
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

        経路統一 (R2c) で full wiring (LlmAgentOrchestrator) は退役し、本 escape 経路が
        唯一の turn 実行経路になった。本テーブルが tool ディスパッチの SSOT である。
        """
        handler = self._tool_handlers.get(name)
        if handler is None:
            # PR-J: LLM の tool 名 typo を救済する 3 層:
            # 1. fuzzy suggestion で近い候補を message に追記
            # 2. valid tool 一覧を併記 (想像由来 typo の救済)
            # 3. should_reschedule=True で次 tick の起床を確保 (= 配信)
            # 1/2 が無くても 3 (= message を agent に届ける) が無いと意味が
            # ないので、3 が最重要。
            message = build_unsupported_tool_message(
                requested=name,
                valid_tools=self._tool_handlers.keys(),
            )
            # PR-J: should_reschedule は _RESCHEDULE_ERROR_CODES SSOT 経由で
            # 決定する。ハードコードすると将来 policy を変えた時に乖離する。
            return LlmCommandResultDto(
                success=False,
                message=message,
                error_code="UNSUPPORTED_TOOL",
                should_reschedule=is_reschedulable_error_code("UNSUPPORTED_TOOL"),
            )
        return handler(player_id, arguments, runtime_context)

    # ── per-tool handlers (PR 7) ──

    # PR-θ1/θ2 (経路統合): _handle_travel_to / _handle_explore は削除。
    # SpotGraphToolExecutor._travel_to / _explore に統合され、それぞれ
    # runtime.do_move / runtime.do_explore を呼ぶ薄い wrapper として単一の
    # 実装になった。旧 handler の副作用 (scene_boundary / subjective /
    # _process_graph_events / display_name / 発見なし時の可視 object 併記 /
    # inner_thought 空警告) は全部保持している。
    #
    # 可視 object 併記は executor が runtime_context.targets を受け取れる
    # よう SpotGraphToolExecutor handlers の signature を
    # ``(int, args, runtime_context=None)`` に拡張して対応した。
    # travel_to は SpotGraphArgumentResolver._resolve_travel_to が
    # resolver stage で destination_label → destination_spot_id に解決する
    # (resolver_targets に含まれる)。

    # PR-θ3 (経路統合): _handle_interact は削除。SpotGraphToolExecutor._interact
    # に統合され、runtime.do_interact を呼ぶ薄い wrapper として単一の
    # interact 実装になった。旧 handler の副作用 (label→object_id resolve /
    # SpotObjectInteractedEvent / _process_graph_events / _record_action_result /
    # InteractionNotAllowedException 用の reason-based remediation /
    # InteractionNotFoundException 用の 利用可能操作列挙 / inner_thought
    # 空警告) は全部保持している。
    #
    # label→object_id resolve は SpotGraphArgumentResolver._resolve_interact
    # が resolver stage で行い、新経路には object_id (int) が届く。
    # resolver_targets に TOOL_NAME_SPOT_GRAPH_INTERACT を含めた。resolver
    # 例外時の「有効な object_label 一覧」message は
    # _build_interact_invalid_label_failure が組み立てる。
    # LLM 向け remediation helper (interact_remediation_for_reason /
    # list_object_interactions) は application 層 (interact_helpers.py) に
    # 移動した。

    # PR-θ4 (経路統合): _handle_listen は削除。SpotGraphToolExecutor._listen
    # に統合され、runtime.do_listen を呼ぶ薄い wrapper として単一の実装に
    # なった。旧 handler の副作用 (event 差分カウント / _process_graph_events /
    # inner_thought 空警告) は保持している。

    def _handle_wait(
        self,
        player_id: PlayerId,
        arguments: dict[str, Any],
        runtime_context: Any,
    ) -> LlmCommandResultDto:
        del runtime_context  # unused — wait は targets を見ない
        reason = str(arguments.get("reason", "")).strip()
        # #471 fix: do_wait は world tick を進めなくなった。返り値は現在 tick。
        # message も「時間が進んだ」ではなく「今ターンは行動を控えた」に変更し、
        # LLM に対しても「wait は時間進行のショートカットではない」ことを示す。
        tick = self.runtime.do_wait(
            player_id, reason=reason, **extract_subjective_action_fields(arguments)
        )
        suffix = f"（理由: {reason}）" if reason else ""
        return with_inner_thought_empty_warning(
            TOOL_NAME_SPOT_GRAPH_WAIT,
            arguments,
            LlmCommandResultDto(
                success=True,
                message=f"今ターンは行動を控えた: tick={tick}{suffix}",
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
        # PR-J: ``UNSUPPORTED_TOOL`` を ``_RESCHEDULE_ERROR_CODES`` に追加した
        # ため、デフォルトのままだと「永続的に無効な機能」も reschedule され
        # てしまう。本ハンドラは「脱出ランタイムでは恒久的に未対応」を表す
        # 経路なので、明示的に ``should_reschedule=False`` を立てて agent を
        # 即時 chain 終了させる (= 同じ無駄を 5 回繰り返さない)。
        return LlmCommandResultDto(
            success=False,
            message="サブロケーション変更は脱出ランタイムでは未対応です。",
            error_code="UNSUPPORTED_TOOL",
            should_reschedule=False,
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
        # (world_runtime._time_label) があるのでそれに委譲する。
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

        # PR #450: world_runtime は demos/ から application/ に移動済。
        # presentation 層が demos/ を import する旧構造を解消する。
        from ai_rpg_world.application.world_runtime.world_runtime import (
            create_world_runtime,
        )

        world_character = None
        if request.character_ids:
            detail = self.get_character(request.character_ids[0])
            world_character = _character_to_prompt_input(detail)

        runtime = create_world_runtime(
            scenario_path, world_character=world_character
        )
        spawn_ids = frozenset(int(sp.player_id) for sp in runtime.scenario.player_spawns)
        llm_resolver = _WorldSpawnAllPlayersLlmResolver(spawn_player_ids=spawn_ids)
        # appender / turn_scheduler は heartbeat と ActionFailed の両方で
        # 共有する (同じ observation buffer に書き込み、同じ turn trigger を
        # 呼ぶため)。
        appender = ObservationAppender(runtime._obs_buffer)
        # 注意: llm_wiring を構築する前に turn_scheduler を作る必要がある
        # ため、最初に空の wiring を作り、それから scheduler / emitter を
        # 組み立てて wiring に注入する流れにする。
        llm_wiring = _WorldLlmWiring(
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
            interval_ticks=_resolve_llm_idle_timeout_ticks(),
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
