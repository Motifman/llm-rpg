"""episodic 受動想起 section の本文組み立てと trace。"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    SystemPromptPlayerInfoDto,
)
from ai_rpg_world.application.llm.services.episodic_cue_rules import build_situation_episodic_cues
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
    EpisodicPassiveRecallRetrievalDebug,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
    from ai_rpg_world.domain.being.value_object.being_id import BeingId

# PR7 (R4): noun_matcher に通す追加テキストの上限。直近 N 件の観測 / 行動結果
# を対象にする。長すぎる prose は per-text char cap で打ち切り、Aho-Corasick
# の線形性を信じても pathological 入力で時間爆発しないようにする。
_R4_RECENT_FREETEXT_LIMIT = 5
_R4_PER_TEXT_CHAR_CAP = 2048

_module_logger = logging.getLogger(__name__)


def _gather_additional_freetexts_for_recall(
    observations: list[ObservationEntry],
    action_results: list[ActionResultEntry],
) -> list[str]:
    """PR7 (R4): recall 用に noun_matcher に通す追加文字列を集める。

    対象:
    - 直近 ``_R4_RECENT_FREETEXT_LIMIT`` 件の観測 prose ([1:] = 最新を除く。
      最新は別途 ``observation_prose`` として渡されるため重複させない)
    - 直近 ``_R4_RECENT_FREETEXT_LIMIT`` 件の行動結果の action_summary +
      result_summary (= 自分の speech / inner_thought / その他ツール発話の
      文字列)

    NOTE: ``action_results[0]`` は ``build_situation_episodic_cues`` に
    ``latest_action`` として別途渡されるが、そちらの経路は tool_name と outcome
    の cue を立てるだけで **action_summary / result_summary の自由文に対しては
    noun_matcher を当てない**。よってここで `[0]` を含めるのが正しい (= noun
    抽出パスはこちらが唯一)。下流 ``_validate_and_dedupe`` で重複 cue は 1 件化
    されるので最終 cue 列に重複は出ない。

    各テキストは ``_R4_PER_TEXT_CHAR_CAP`` 文字に切る (pathological prose
    での matcher 時間爆発を避ける safety cap)。
    """
    out: list[str] = []
    # observations は新しい順なので [0] は除いて [1:LIMIT+1] を取る
    for entry in observations[1 : _R4_RECENT_FREETEXT_LIMIT + 1]:
        prose = entry.output.prose
        if prose:
            out.append(prose[:_R4_PER_TEXT_CHAR_CAP])
    for ar in action_results[:_R4_RECENT_FREETEXT_LIMIT]:
        if ar.action_summary:
            out.append(ar.action_summary[:_R4_PER_TEXT_CHAR_CAP])
        if ar.result_summary:
            out.append(ar.result_summary[:_R4_PER_TEXT_CHAR_CAP])
    return out


def _join_passive_recall_texts(
    candidates: tuple[EpisodicPassiveRecallCandidate, ...],
) -> str:
    """retrieve の候補順のまま、各 episode の recall text を改行で連結する。"""
    parts: list[str] = []
    for cand in candidates:
        raw = cand.episode.recall_text
        text = raw.strip() if isinstance(raw, str) else ""
        if text:
            game_time_label = cand.episode.game_time_label
            if isinstance(game_time_label, str) and game_time_label.strip():
                text = f"[{game_time_label.strip()}] {text}"
            parts.append(text)
    return "\n".join(parts)


def emit_episodic_recall_trace(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    situation_cues: tuple[Any, ...],
    candidates: list[Any],
    relevant_memories_text: str = "",
    retrieval_debug: EpisodicPassiveRecallRetrievalDebug | None = None,
) -> None:
    """``EPISODIC_RECALL`` を trace に記録する (失敗は握りつぶす)。

    ``relevant_memories_text`` は実 prompt に注入された連結後テキスト。
    recall 1 件あたりの注入サイズ ÷ prompt_tokens を post-hoc に出すための
    計測点 (実験 #356 後続: cached_tokens / TTFT 分析と組合せる)。

    ``retrieval_debug`` が与えられれば、検索 axis ごとの raw 件数・
    max_cap 前 union 件数・最終 candidate の source_axes 別件数を
    payload に追加で乗せる (#526 後続: cue 設計の post-hoc 解析用)。
    既定 ``None`` のときは payload に追加キーを足さず、既存の trace
    読み手 (viewer / jq クエリ) を破らない。
    """
    recorder = builder._resolve_trace_recorder()
    if recorder is None:
        return
    tick: int | None = None
    if builder._current_tick_provider is not None:
        try:
            tick = builder._current_tick_provider()
        except Exception:
            tick = None
    try:
        cue_keys = [c.to_canonical() for c in situation_cues]
    except Exception:
        cue_keys = []
    cand_payload: list[dict[str, Any]] = []
    for cand in candidates:
        try:
            ep = cand.episode
            ep_id = getattr(ep, "episode_id", "")
            cand_payload.append(
                {
                    "episode_id": ep_id,
                    "source_axes": list(cand.source_axes),
                    "recall_text_snippet": (getattr(ep, "recall_text", "") or "")[:120],
                }
            )
        except Exception:
            continue
    # debug 由来の追加キーは ``retrieval_debug`` が与えられたときだけ
    # 載せる (= 既存 trace 読み手の non-strict 互換)。
    debug_kwargs: dict[str, Any] = {}
    if retrieval_debug is not None:
        try:
            debug_kwargs["raw_row_count_by_axis"] = {
                axis: count for axis, count in retrieval_debug.raw_row_count_by_axis
            }
            debug_kwargs["union_episode_count_before_max_cap"] = (
                retrieval_debug.union_episode_count_before_max_cap
            )
            debug_kwargs["final_episode_count_by_source_axis"] = {
                axis: count
                for axis, count in retrieval_debug.final_episode_count_by_source_axis
            }
        except Exception:
            # debug 構造が想定外でも recall trace 本体は落とさない。
            builder._logger.debug(
                "retrieval_debug の payload 化に失敗; 既存キーのみで emit します",
                exc_info=True,
            )
            debug_kwargs = {}
    try:
        recorder.record(
            TraceEventKind.EPISODIC_RECALL,
            tick=tick,
            player_id=int(player_id.value),
            situation_cues=cue_keys,
            candidate_count=len(cand_payload),
            candidates=cand_payload,
            recall_text_chars_total=len(relevant_memories_text or ""),
            **debug_kwargs,
        )
    except Exception:
        # 例: recorder が新しい kind を未知扱いで例外を投げる等。
        # prompt build を止めない方針を維持しつつ、recorder 側のバグを
        # 後追いできるよう DEBUG 級で痕跡を残す (logger は親クラスから)。
        builder._logger.debug(
            "trace recorder.record raised for EPISODIC_RECALL; skipping",
            exc_info=True,
        )


def run_episodic_passive_recall(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    being_id: BeingId,
    observations: list[ObservationEntry],
    action_results: list[Any],
    ui_context: Any,
    current_state_text: str,
    recent_events_text: str,
    player_info: SystemPromptPlayerInfoDto,
    current_state_dto: Any | None = None,
) -> tuple[str, int | None]:
    """受動想起ブロックを実行し、(関連する記憶テキスト, 候補件数) を返す。

    Issue #227 後続レビュー (Prompt MEDIUM-5) で build() 本体から抽出。
    responsibilities:
    1. situation_cues を runtime_context + 直近観測 + 直近 action から組む
    2. passive_recall.retrieve で候補 episode を取得
    3. 候補を改行で連結して relevant_memories_text を作る
    4. memory_link_service があれば passive recall 通知を流す

    候補件数は ``None`` で 「機構自体が未注入」 を表す (= 「0 件しか
    浮かばなかった」 と意味が異なる)。 ``int`` で 「機構は走ったが N 件」
    を表す。 sentinel int を避けて Optional で区別する。
    """
    if builder._episodic_passive_recall is None:
        return "", None

    observation_structured = None
    observation_prose: str | None = None
    if observations:
        observation_structured = observations[0].output.structured
        observation_prose = observations[0].output.prose
    latest_action = action_results[0] if action_results else None
    additional_freetexts = _gather_additional_freetexts_for_recall(
        observations, action_results
    )
    encounter_tick = builder._resolve_encounter_tick()
    situation_cues = build_situation_episodic_cues(
        runtime_context=ui_context.tool_runtime_context,
        observation_structured=observation_structured,
        latest_action=latest_action,
        observation_prose=observation_prose,
        noun_matcher=builder._noun_matcher,
        additional_freetexts=additional_freetexts,
        encounter_memory=builder._encounter_memory_for_recall,
        encounter_player_id=player_id,
        encounter_current_tick=encounter_tick,
        encounter_recent_window_ticks=builder._encounter_recent_window_ticks,
        encounter_spot_id_resolver=builder._encounter_spot_id_resolver,
        recently_met_names=builder._recently_met_names(player_id),
    )
    recall_now = datetime.now(timezone.utc)
    # PR5 (R1): sliding window にまだ生きている直近 episode を recall から
    # 排除するため、最古 entry の occurred_at を時間下限として渡す。entry
    # が空のとき (= 起動直後) は None。安全 floor (= 最低 5 tick / scenario の
    # 1 tick 相当秒に変換) は加味せず、現時点の最古 entry 自身を境界に
    # 倒す。「境界 episode 自身は recall から外す」という保守的な側に倒す。
    #
    # 防衛: IShortTermMemory 実装やテスト mock が default で None /
    # 不正な型を返すことがある。``None`` 以外で ``datetime`` でなければ、
    # 「実装側のバグ」として warning ログを残し、recall の時間下限フィルタを
    # off に倒す。silent fallback ではなく "noisy" な degradation にして、
    # ログから発見できるようにする。
    raw_oldest = builder._short_term_memory.get_oldest_entry_datetime(player_id)
    if raw_oldest is not None and not isinstance(raw_oldest, datetime):
        _module_logger.warning(
            "IShortTermMemory.get_oldest_entry_datetime returned "
            "unexpected type %s for player_id=%s; recall の時間下限フィルタ "
            "を off にして fallback します。",
            type(raw_oldest).__name__,
            player_id.value,
        )
        raw_oldest = None
    min_recall_dt: datetime | None = raw_oldest
    recall_result = builder._episodic_passive_recall.retrieve(
        being_id=being_id,
        situation_cues=situation_cues,
        limit_per_axis=builder._episodic_passive_recall_limit_per_axis,
        max_candidates=builder._episodic_passive_recall_max_candidates,
        now=recall_now,
        min_occurred_at=min_recall_dt,
    )
    relevant_memories_text = _join_passive_recall_texts(recall_result.candidates)

    # Issue #283 後続: recall 結果を trace に残す (Viewer / jq から
    # 「どのエピソードが想起されたか」を後追いできる)。candidates が 0
    # でも「recall を試行したが結果は 0」事実は残しておく価値があるので emit。
    # #526 後続: ``retrieval_debug`` を渡し、cue 設計の post-hoc 解析
    # (axis 別 raw 件数 / union 件数 / source_axes 別件数) を可視化する。
    emit_episodic_recall_trace(
        builder,
        player_id=player_id,
        situation_cues=situation_cues,
        candidates=list(recall_result.candidates),
        relevant_memories_text=relevant_memories_text,
        retrieval_debug=recall_result.debug,
    )

    if builder._episodic_memory_link_service is not None and recall_result.candidates:
        builder._episodic_memory_link_service.on_passive_recall_candidates(
            player_id.value,
            being_id,
            recall_result.candidates,
            now=recall_now,
        )

    # Issue #526 後続: 候補 0 件のときも「受動想起の機構は走ったが何も
    # 浮かばなかった」事実を agent 側で可観測にする。``_episodic_passive_recall``
    # 未注入時は上の早期 return で空文字を返しており、ここには到達しない。
    candidate_count = len(recall_result.candidates)
    if not relevant_memories_text.strip():
        relevant_memories_text = "(受動想起では何も浮かばなかった)"
    return relevant_memories_text, candidate_count
