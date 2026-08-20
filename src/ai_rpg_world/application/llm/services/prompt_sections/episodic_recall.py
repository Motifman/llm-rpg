"""episodic 受動想起 section の本文組み立てと trace。"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    SystemPromptPlayerInfoDto,
)
from ai_rpg_world.application.llm.services.afterglow_store import make_afterglow_handle
from ai_rpg_world.application.llm.services.episodic_cue_rules import build_situation_episodic_cues
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
    EpisodicPassiveRecallRetrievalDebug,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import (
    EpisodicReinterpretationJournalRepository,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.domain.being.value_object.being_id import BeingId
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder

# PR7 (R4): noun_matcher に通す追加テキストの上限。直近 N 件の観測 / 行動結果
# を対象にする。長すぎる prose は per-text char cap で打ち切り、Aho-Corasick
# の線形性を信じても pathological 入力で時間爆発しないようにする。
_R4_RECENT_FREETEXT_LIMIT = 5
_R4_PER_TEXT_CHAR_CAP = 2048

_module_logger = logging.getLogger(__name__)


def _gather_additional_freetexts_for_recall(
    observations: List[ObservationEntry],
    action_results: List[ActionResultEntry],
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


def _format_afterglow_section(
    afterglow_index: Optional[tuple[Any, ...]],
) -> str:
    """afterglow index を 1 行見出しの section text に整形する。

    None / 空のときは空文字を返し、上位は section ごと省略する。各エントリは
    ``[handle] heading`` 形式の 1 行で並べ、LLM から「ぼんやり覚えてる
    記憶」として visible にする。handle は make_afterglow_handle で生成され、
    同じ episode は常に同じ handle になる (= 後続 PR の能動想起ツールで
    安定して引ける)。
    """
    if not afterglow_index:
        return ""
    lines = [
        "【さっき思い出した記憶の見出し】(鮮明には浮かばないが、ヒントとして残っている)",
        "気になる見出しがあれば memory_recall_by_handle にその handle を渡して本文を引き戻せる。",
    ]
    for entry in afterglow_index:
        handle = make_afterglow_handle(entry.episode_id)
        lines.append(f"- [{handle}] {entry.heading}")
    return "\n".join(lines)


def _join_passive_recall_texts(
    player_id: int,
    candidates: tuple[EpisodicPassiveRecallCandidate, ...],
    journal_store: EpisodicReinterpretationJournalRepository | None = None,
    *,
    being_id: Optional["BeingId"] = None,
) -> str:
    """retrieve の候補順のまま、active 再解釈を優先して recall text を改行で連結する。

    Phase 3 Step 3d-3: legacy player_id 経路は撤去済。``being_id`` が ``None``
    の場合は journal をスキップして生の ``recall_text`` を使う (= prompt
    強化の graceful degradation)。``journal_store`` 自体が ``None`` の場合も
    同じく生 recall に縮退する。

    ``player_id`` は warning ログ用に保持 (journal 走査は being_id 経由のみ)。
    後続フェーズで Being の player_id 逆引きが容易になった場合は引数から
    削除可能。
    """
    parts: list[str] = []
    for cand in candidates:
        active = None
        if journal_store is not None and being_id is not None:
            try:
                active = journal_store.get_active_by_being(
                    being_id, cand.episode.episode_id
                )
            except Exception:
                # 再解釈 store の障害で recall を止めず生の recall_text に縮退する。
                # 「sail と active が drift している」状況を後追いできるよう WARN
                # で traceback ごと残す (silent failure 防止)。
                _module_logger.warning(
                    "journal_store.get_active_by_being failed for player=%s "
                    "episode=%s; falling back to raw recall_text",
                    player_id,
                    cand.episode.episode_id,
                    exc_info=True,
                )
                active = None
        raw = active.current_recall_text if active is not None else cand.episode.recall_text
        text = raw.strip() if isinstance(raw, str) else ""
        if text:
            game_time_label = cand.episode.game_time_label
            if isinstance(game_time_label, str) and game_time_label.strip():
                text = f"[{game_time_label.strip()}] {text}"
            parts.append(text)
    return "\n".join(parts)


def append_recall_observation(
    builder: "DefaultPromptBuilder",
    being_id: Optional["BeingId"],
    observation: EpisodicRecallObservation,
) -> None:
    """recall observation を recall_buffer_store に書く helper。

    Phase 3 Step 3d-3: legacy player_id 経路は撤去済。Being 未解決時は
    silent skip (= prompt 強化の graceful fallback、turn は止めない)。
    ``builder._episodic_recall_buffer_store is None`` は呼出側で先に弾く前提。

    ``being_id is None`` 時のデバッグ可視性は、呼出側 ``run_episodic_passive_recall``
    で 1 回の warning ログとして残す (= silent failure 構造的対処)。
    """
    assert builder._episodic_recall_buffer_store is not None
    if being_id is None:
        return
    builder._episodic_recall_buffer_store.append_by_being(being_id, observation)


def emit_episodic_recall_trace(
    builder: "DefaultPromptBuilder",
    *,
    player_id: PlayerId,
    situation_cues: tuple,
    candidates: list,
    relevant_memories_text: str = "",
    retrieval_debug: Optional[EpisodicPassiveRecallRetrievalDebug] = None,
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
    tick: Optional[int] = None
    if builder._current_tick_provider is not None:
        try:
            tick = builder._current_tick_provider()
        except Exception:
            tick = None
    try:
        cue_keys = [c.to_canonical() for c in situation_cues]
    except Exception:
        cue_keys = []
    # PR-E (Y_after_issue621 後続): habituation_penalty を per-candidate に
    # 埋め込み、recall ランキングの動きを 1 つの candidate だけで読めるよう
    # にする。retrieval_debug が無い (= 旧経路) ときは全候補 penalty=0。
    penalty_by_ep: dict[str, int] = {}
    if retrieval_debug is not None:
        try:
            penalty_by_ep = {
                eid: penalty
                for eid, penalty in retrieval_debug.habituation_penalty_by_episode
            }
        except Exception:
            penalty_by_ep = {}
    cand_payload: list[dict] = []
    for cand in candidates:
        try:
            ep = cand.episode
            ep_id = getattr(ep, "episode_id", "")
            cand_payload.append(
                {
                    "episode_id": ep_id,
                    "source_axes": list(cand.source_axes),
                    "recall_text_snippet": (getattr(ep, "recall_text", "") or "")[:120],
                    # PR-E: dict に未登録なら罰則なし扱い (= 0)。
                    "habituation_penalty": penalty_by_ep.get(ep_id, 0),
                }
            )
        except Exception:
            continue
    # debug 由来の追加キーは ``retrieval_debug`` が与えられたときだけ
    # 載せる (= 既存 trace 読み手の non-strict 互換)。
    debug_kwargs: dict = {}
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
            # #526 段階 2 (PR #565) 続き: 慣化ペナルティが適用された
            # episode の (id → penalty 値) も載せる。PR #565 で dataclass
            # field は追加されたが本 emission code は更新漏れだったため、
            # ペナルティが trace から見えず「慣化が動いているか」の判定が
            # 不可能になっていた。
            debug_kwargs["habituation_penalty_by_episode"] = {
                eid: penalty
                for eid, penalty in retrieval_debug.habituation_penalty_by_episode
            }
            # #526 段階 3: 想起スロットの 1 tick 分の動きを trace に残す。
            # off 時は decision=None なので何も書かない (= 既存挙動)。
            slot_decision = retrieval_debug.recall_slot_decision
            if slot_decision is not None:
                debug_kwargs["recall_slot"] = {
                    "retained": [
                        {"episode_id": e.episode_id, "entered_tick": e.entered_tick}
                        for e in slot_decision.retained
                    ],
                    "inserted": [
                        {"episode_id": e.episode_id, "entered_tick": e.entered_tick}
                        for e in slot_decision.inserted
                    ],
                    "evicted_ids": list(slot_decision.evicted_ids),
                    "new_slot_size": len(slot_decision.new_slot),
                }
            # #526 段階 3 PR-C: afterglow index の状態を trace に乗せる。
            # off 時は index=None なので key 自体を出さない (= 既存挙動)。
            afterglow_index = retrieval_debug.afterglow_index
            if afterglow_index is not None:
                debug_kwargs["afterglow"] = {
                    "size": len(afterglow_index),
                    "entries": [
                        {
                            "episode_id": e.episode_id,
                            "heading": e.heading,
                            "entered_tick": e.entered_tick,
                            "source": e.source.value,
                        }
                        for e in afterglow_index
                    ],
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
    observations: List[ObservationEntry],
    action_results: List[Any],
    ui_context: Any,
    current_state_text: str,
    recent_events_text: str,
    player_info: SystemPromptPlayerInfoDto,
    current_state_dto: Optional[Any] = None,
    prediction_context_id: Optional[str] = None,
) -> tuple[str, Optional[int], tuple[str, ...]]:
    """受動想起ブロックを実行し、(関連する記憶テキスト, 候補件数, episode_id 群) を返す。

    ``prediction_context_id`` が渡されたとき、生成する各
    ``EpisodicRecallObservation`` にその id を stamp する (U1 部品5: この
    episode を想起した prompt build で立てた予測をあとで辿るため)。None なら
    stamp しない (= id 機構 OFF)。

    Issue #227 後続レビュー (Prompt MEDIUM-5) で build() 本体から抽出。
    responsibilities:
    1. situation_cues を runtime_context + 直近観測 + 直近 action から組む
    2. passive_recall.retrieve で候補 episode を取得
    3. 候補を改行で連結して relevant_memories_text を作る
    4. memory_link_service があれば passive recall 通知を流す
    5. recall_buffer_store があれば EpisodicRecallObservation を append

    候補件数は ``None`` で 「機構自体が未注入」 を表す (= 「0 件しか
    浮かばなかった」 と意味が異なる)。 ``int`` で 「機構は走ったが N 件」
    を表す。 sentinel int を避けて Optional で区別する。
    """
    if builder._episodic_passive_recall is None:
        return "", None, ()

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
    min_recall_dt: Optional[datetime] = raw_oldest
    # #526 段階 2: 慣化ペナルティのため現在 tick を retrieve に渡す。
    # provider が None / 例外を返したときは慣化を skip (= 既存挙動)。
    current_tick_for_habituation: Optional[int] = None
    if builder._current_tick_provider is not None:
        try:
            tick_val = builder._current_tick_provider()
            if isinstance(tick_val, int) and not isinstance(tick_val, bool):
                current_tick_for_habituation = tick_val
        except Exception:
            builder._logger.debug(
                "current_tick_provider raised; habituation を skip して進む",
                exc_info=True,
            )
    recall_result = builder._episodic_passive_recall.retrieve(
        being_id=being_id,
        situation_cues=situation_cues,
        limit_per_axis=builder._episodic_passive_recall_limit_per_axis,
        max_candidates=builder._episodic_passive_recall_max_candidates,
        now=recall_now,
        min_occurred_at=min_recall_dt,
        current_tick=current_tick_for_habituation,
    )
    relevant_memories_text = _join_passive_recall_texts(
        player_id.value,
        recall_result.candidates,
        builder._episodic_reinterpretation_journal_store,
        being_id=being_id,
    )

    # #526 段階 3 PR-C: afterglow index を 1 行見出しの section として連結。
    # 「鮮明な記憶」(= recall_text の本文) の後ろに「さっき思い出した記憶の
    # 見出し」を並べ、LLM に「ぼんやり覚えてる」の層が見える形にする。
    # afterglow off / 空のときは何も足さない。
    afterglow_text = _format_afterglow_section(
        recall_result.debug.afterglow_index
    )
    if afterglow_text:
        if relevant_memories_text:
            relevant_memories_text = (
                f"{relevant_memories_text}\n\n{afterglow_text}"
            )
        else:
            relevant_memories_text = afterglow_text

    # #526 段階 2: 慣化 sidecar の更新は retrieve 後に呼び出し側で行う
    # (retrieve は read-only を保つ)。store / being_id / tick が揃った
    # ときだけ書き込み、いずれかが欠ければ silent skip。
    if (
        builder._episodic_recall_habituation_store is not None
        and being_id is not None
        and current_tick_for_habituation is not None
        and recall_result.candidates
    ):
        try:
            builder._episodic_recall_habituation_store.record_recall(
                being_id,
                [c.episode.episode_id for c in recall_result.candidates],
                current_tick_for_habituation,
            )
        except Exception:
            # sidecar 書き込み失敗は recall 自体を止めない (graceful)。
            builder._logger.warning(
                "habituation_store.record_recall failed; recall は完走しました",
                exc_info=True,
            )

    # #526 段階 3: 想起スロット sidecar の更新も retrieve 後に行う。
    # retrieve 内で apply_slot_policy の結果が ``debug.recall_slot_decision``
    # に乗っているので、それを store に反映する。slot off (= decision None)
    # のときは silent skip。
    slot_decision = recall_result.debug.recall_slot_decision
    if (
        builder._episodic_recall_slot_store is not None
        and being_id is not None
        and current_tick_for_habituation is not None
        and slot_decision is not None
    ):
        try:
            builder._episodic_recall_slot_store.apply_decision(
                being_id,
                slot_decision,
                current_tick=current_tick_for_habituation,
                cooldown_ticks=builder._episodic_recall_slot_cooldown_ticks,
            )
        except Exception:
            builder._logger.warning(
                "recall_slot_store.apply_decision failed; recall は完走しました",
                exc_info=True,
            )

    # #526 段階 3 PR-C: afterglow store の更新も retrieve 後に行う。
    # retrieve service が apply_afterglow_policy の結果を
    # ``debug.afterglow_index`` に乗せているので、それを store へ反映する。
    # afterglow off のときは index が None なので silent skip。
    afterglow_index = recall_result.debug.afterglow_index
    if (
        builder._afterglow_store is not None
        and being_id is not None
        and afterglow_index is not None
    ):
        try:
            builder._afterglow_store.apply_decision(being_id, afterglow_index)
        except Exception:
            builder._logger.warning(
                "afterglow_store.apply_decision failed; recall は完走しました",
                exc_info=True,
            )

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

    if builder._episodic_recall_buffer_store is not None:
        turn_index = (
            builder._episodic_turn_index_provider(player_id)
            if builder._episodic_turn_index_provider is not None
            else 0
        )
        situation_cue_keys = tuple(c.to_canonical() for c in situation_cues)
        # Phase 3 Step 3d-3: legacy 経路は撤去済。Being 未解決時は
        # `_append_recall_observation` が silent skip する (turn は継続)。
        # 未解決をデバッグ可能にするため、ここで 1 度だけ warning ログを
        # 残す (= 候補ごとには出さず recall buffer 全体への記録試行と
        # して 1 回。silent failure 構造的対処、design_decisions.md #5)。
        if being_id is None and recall_result.candidates:
            builder._logger.warning(
                "episodic_recall_buffer skipped: being_id unresolved "
                "(player_id=%s, candidates=%d). 再解釈 sidecar は動かないが "
                "turn は継続する。",
                player_id.value,
                len(recall_result.candidates),
            )
        for cand in recall_result.candidates:
            try:
                observation = EpisodicRecallObservation(
                    recall_id=f"recall-{uuid4().hex}",
                    player_id=player_id.value,
                    episode_id=cand.episode.episode_id,
                    recalled_at=datetime.now(timezone.utc),
                    source_axes=cand.source_axes,
                    current_state_snapshot=current_state_text,
                    recent_events_snapshot=recent_events_text,
                    persona_snapshot=player_info.persona_block,
                    situation_cues=situation_cue_keys,
                    turn_index=turn_index,
                    prediction_context_id=prediction_context_id,
                )
                append_recall_observation(builder, being_id, observation)
            except Exception as e:
                builder._logger.warning(
                    "Failed to record episodic recall observation; prompt build continues: %s",
                    e,
                    exc_info=True,
                )

    # Issue #526 後続: 候補 0 件のときも「受動想起の機構は走ったが何も
    # 浮かばなかった」事実を agent 側で可観測にする。``_episodic_passive_recall``
    # 未注入時は上の早期 return で空文字を返しており、ここには到達しない。
    candidate_count = len(recall_result.candidates)
    if not relevant_memories_text.strip():
        relevant_memories_text = "(受動想起では何も浮かばなかった)"

    # U1 (部品5 想起の信用割り当ての土台): この build で in-context だった
    # episode_id 群を prediction_context_id に紐づけるため呼び出し元へ返す。
    episode_ids = tuple(c.episode.episode_id for c in recall_result.candidates)
    return relevant_memories_text, candidate_count, episode_ids
