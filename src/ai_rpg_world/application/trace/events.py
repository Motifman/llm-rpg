"""Trace event の型定義 (Issue #188 Phase 1d)。

シナリオ実行ログを後から振り返るための「人間向けタイムライン」の構成単位。
LLM 内部ステート (sliding_window や action_result) とは別系統の、薄い記録層。

設計指針:
- 1 種類の dataclass + ``kind`` 文字列で十分。ドメインイベントのような複雑な
  階層は持たない (後から拡張しやすい)
- payload は ``Dict[str, Any]``: 各 kind ごとに緩く決めて JSONL に出す
- 時刻は ISO 8601 文字列で持つ (JSONL を grep / jq しやすくするため)
- tick / player_id は None を許容: tick 跨ぎの世界イベントや、playerに紐づか
  ない system event も同じ列に流せるようにする
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TraceEventKind:
    """``TraceEvent.kind`` に入れる文字列定数群。

    enum にしないのは、後から外部スクリプトが新しい kind を勝手に流す自由を
    残すため (JSONL なので緩く)。よく使う既知値だけここに集める。
    """

    # 非同期のハンドラが失敗したか、仕事を受け付けなかった。1 件ごとに 1 件。payload: reason
    # (prepare_failed / handler_failed / application_failed / capacity / shutdown / shutdown_timeout) /
    # recipient_key / event_id / event_type / handler / error_type / error_message (design_decisions D1824-15)。
    ASYNC_EVENT_DELIVERY_FAILED = "async_event_delivery_failed"
    RUN_START = "run_start"
    RUN_END = "run_end"
    TICK_START = "tick_start"
    TICK_END = "tick_end"
    OBSERVATION = "observation"
    ACTION = "action"
    ACTION_RESULT = "action_result"
    MEMO_HINT = "memo_hint"
    # #1628: 環境の tool の引数 memo を読んだ 1 回。引数を書かなかった呼び出しでは出さない。
    # payload: being_id / turn / tool / environment_name /
    #   applied: list[{index, do, handle, kind, text, provenance}] (消した操作は消したメモ) /
    #   rejected: list[{index, reason, raw, detail}] (形が崩れた操作と、メモ帳が受け付けなかった操作) /
    #   skipped_reason: "no_acting_being" | "writing_failed" | None / error
    BEING_MEMO = "being_memo"
    # #1319: 型付きの判断 (Noul / Choice / Score) を引いた 1 件。
    # payload: question / original / chosen / probability / confidence /
    # min_confidence / accepted / latency_ms / source / unavailable_reason。
    #
    # **採らなかった判断と、得られなかった判断も残す。** 採用分だけ残すと、
    # OFF の run と全件 fallback の run が trace で見分けられず、閾値を動かす
    # 判断ができない。
    TYPED_JUDGMENT = "typed_judgment"
    # #1641: 人を対象にした操作の引数 item を、正式な名前どおりでなく相手の所持品へ
    # 当てようとした 1 件。正式な名前で当たったときは出さない。
    # payload: action_name / target_player_id / written /
    #   outcome: "resolved" | "ambiguous" | "absent" | "unrecognized" /
    #   method: "exact" | "partial" | "judgment" | "official_name_of_other_item" |
    #   "nothing_held" | "no_judge" (後ろの 3 つは absent と言い切った理由) /
    #   resolved_name / matched_names /
    #   rescue_wired (意味の判断が配線されていたか) /
    #   judgment: {chosen, probability, confidence, min_confidence, accepted, latency_ms,
    #   source, unavailable_reason} | None
    ITEM_NAME_RESOLUTION = "item_name_resolution"
    # Issue #240 後続: 同一 (tool, fingerprint) の連打を loop guard が検知し
    # 警告観測を注入したタイミング。trace で wait spam の抑制動作を可視化する。
    # payload: tool_name / argument_fingerprint / consecutive_count
    LOOP_GUARD_WARNING = "loop_guard_warning"
    NOTE = "note"
    # Phase 1d viewer: プレイヤーがスポット間を移動した瞬間。空間アニメーション
    # 描画に使う。payload は ``from_spot_id`` / ``to_spot_id`` / ``spot_name`` /
    # ``player_name`` を持つ (run の最初の初期配置は from_spot_id=None で emit)。
    POSITION_CHANGE = "position_change"
    # 予約の後に区間が閉じ、その手前で移動を取りやめた (#1559)。payload は
    # connection_id / connection_name / passage_kind / passage_state / reason /
    # condition_message と、区間の両端と最終の行き先の spot id と名前。
    TRAVEL_BLOCKED = "travel_blocked"
    # 経済統合 Phase 3: 市場の掲示板の上で起きたこと。出品・値の付け直し・
    # 約定・取り下げ・期限切れを 1 つの kind にまとめ、payload の ``kind`` で
    # 分ける。**品目ごとの (tick, 単価) の並びを 1 種類の行から組み立てられる**
    # ようにするため。4 つの kind に割ると、時系列を引く側が 4 経路を結合する
    # ことになり、1 つ足し忘れただけで相場が歪む。
    MARKET_ACTIVITY = "market_activity"
    # world tick 終端の空間集計。payload: occupancy_scope / travel_scope /
    # spot_occupancy[] (spot_id / spot_name / player_count) /
    # cumulative_travel_ticks_by_player。
    # 9 室化で「実際に散ったか」「誰が移動時間を負担したか」を測る。
    WORLD_SPATIAL_METRICS = "world_spatial_metrics"
    # 会議の開始・終了。開始は途中終了した run にも残し、終了には区間長と
    # run 内累積会議 tick を載せる。payload は trigger / spot_id / spot_name、
    # 終了側は started_at_tick / ended_at_tick / end_reason / duration_ticks /
    # cumulative_meeting_ticks も持つ。
    MEETING_STARTED = "meeting_started"
    MEETING_ENDED = "meeting_ended"
    # LLM 性能メトリクス (実験 #356 後続): Phase A の LLM 呼び出し 1 件分の
    # 壁時計 latency / token usage / TPS を記録する。
    # payload: model / wall_latency_ms / prompt_tokens / completion_tokens /
    # cached_tokens / tps / success / error_code / cost_usd
    # ``cost_usd`` は OpenRouter 経由時のみ provider 宣告値が乗る (直結 / vLLM では 0.0)。
    # τ_sim の設定根拠データ + scenario ごとの cost 評価に使う。
    # ``finish_reason`` ("length" は出力の上限で打ち切られた呼び出し) は 2026-10-31 より前の trace には無い (#1924)。
    LLM_CALL = "llm_call"
    # #1924: 考えが出力の上限で切れて行動を返せなかった呼び出しを、考えを止めて 1 回だけ呼び直した。
    # payload: phase / truncated_llm_call_id / retry_llm_call_id / reasoning_effort (打ち切られた呼び出しの段階) /
    # outcome (tool_call / no_tool_call / invoke_exception) / returned_tool / retry_finish_reason / error_type
    LLM_OUTPUT_TRUNCATED_RETRY = "llm_output_truncated_retry"
    # 行動を決める呼び出し以外の LLM 呼び出し 1 回ぶん (#1617)。記憶の部品と Jev。
    # llm_call と分けるのは、行動の費用と混ぜず、連続失敗の監視にも数えないため。
    # payload: component (AuxLlmComponent の値) / model / wall_latency_ms /
    # success / error_code / prompt_tokens / completion_tokens / cached_tokens /
    # cost_usd / question_names (Jev の問いの名前)。
    # 応答に無かった値は null。とくに Jev の cost_usd は null で「取れない」を表す。
    AUX_LLM_CALL = "aux_llm_call"
    # aux_llm_call を書けなかった。payload: component / error_type。
    AUX_LLM_CALL_RECORD_FAILED = "aux_llm_call_record_failed"
    # #1595: 呼び出しが失敗した (時間切れを含む) 手番を、次の tick に回したか。
    # 失敗のたびに 1 件。上限に達して回さなかった失敗は rescheduled=False で残る。
    # payload: consecutive_failures / max_consecutive_failures / rescheduled / error_code
    LLM_FAILURE_RETRY = "llm_failure_retry"
    # #1597: 成功した自分の行動のあと、次の tick に手番を回したか。成功した手番ごとに 1 件。
    # payload: rescheduled / reason (succeeded / rest_chosen / traveling / cannot_act)
    OWN_ACTION_FOLLOW_UP = "own_action_follow_up"
    # prompt section の文字数内訳 (実験 #356 後続: prefix cache 分析用)。
    # prompt_builder.build() が messages / tools を組み上げた直後に 1 件記録する。
    # payload: system_chars / objective_chars / known_people_chars / episode_index_chars / current_state_chars /
    # memos_chars / recent_events_chars / backstory_chars (【ここまでのいきさつ】。2026-10-31 より前の trace には無い) /
    # instruction_chars / tools_chars / user_content_chars / messages_total_chars / tools_count
    # 2026-11-01 から、区画ごとの文字数は作業記憶の区画の本文 (見出しの行を除く) から数える (D1630-3)。
    # recent_events_chars は前置きの一文と改行の分だけ増え、常に 0 だった inventory_chars は無くなった。
    # 出来事の本文が空白だけのときは「（なし）」、現在地の文が空のときは「（情報なし）」も数える (前は 0)。
    # #1630 の 4 本目から、objective_chars はシステムプロンプトの【現在の目的】を数え、その分は system_chars に入る (D1630-4)。
    # token 数ではなく char 数で出す: 軽量 / モデル非依存 / deterministic。
    # 分析側で同 turn の prompt_tokens 比に換算する (≒ token 内訳)。
    PROMPT_SECTION_BREAKDOWN = "prompt_section_breakdown"
    # tool_runtime_context が「引数として渡せる」と宣言した文字列が、
    # current_state_text に引用符つきで現れなかった。起動時は即座に
    # 落とすが、run 中の状態変化で発見した場合は実験データを守るため
    # trace に残して続行する。payload: violation_count / violations[]。
    PROMPT_ARGUMENT_CONTRACT_VIOLATION = "prompt_argument_contract_violation"
    # 2026-10-31 より前の trace には、今の短期記憶とその要約の trace も残る (design_decisions D1824-24)。
    # short_term_summary_dropped / short_term_summary_generation_failed / short_term_summary_generated
    # (要約を作れなかった、作った) と short_term_memory_compacted (古いターンを畳んだ)。今は Being の短期記憶の
    # being_short_term_memory_range_filled / being_backstory_written / being_short_term_memory_fold_forced が受け持つ。
    # Phase 7 (Issue #470): Being snapshot save / load。run が前回 snapshot
    # からの続きか・どの player の memory が今 run の trace に乗っているかを
    # post-hoc 分析できるようにする。silent failure 防止用に **必ず** trace に
    # 1 件残す (= load 成功 / 失敗、save 成功 / 失敗いずれの場合も)。
    # SNAPSHOT_LOAD payload:
    #   - directory: str (= --snapshot-load-dir)
    #   - restored_count: int (= 成功した Being 数)
    #   - memory_turns: list[{being_id, memory_turn}] (= 復元した Being ごとの
    #     記憶のターン数)
    #   - source_scenario: str | None (= snapshot 内に書かれていた元シナリオ名。
    #     現 scenario と異なる場合は cross-scenario transfer)
    #   - removed_memory_keys: list[{being_id, counts: {キー: 件数}}] (= 消した
    #     部品の欄を snapshot から捨てた件数。捨てなかった Being は載せない)
    #   - removed_declared_memory_kinds: list[{being_id, counts: {種類: 件数}}] (= 古い
    #     snapshot から読み捨てた記憶の種類の宣言。D1469-1)
    #   - player_beings_source: "world_snapshot" / "being_snapshots" / "startup" (= 誰がどのプレイヤーを動かして
    #     いるかを読んだ先。対応表の欄が無い古い snapshot は Being の snapshot の番号から作り直し、番号も無ければ
    #     起動時の対応表のまま。D1928)
    #   - removed_legacy_identities: list[{being_id, name, first_person}] (= persona の無い
    #     古い snapshot から読み捨てた仮の名前と一人称。人柄は起動時にシナリオから入れたものを使う。D1469-2)
    # SNAPSHOT_SAVE payload:
    #   - directory: str (= --snapshot-save-dir)
    #   - succeeded_count: int
    #   - failed_count: int
    #   - failures: list[{being_id, error}]
    #   - memory_turns: SNAPSHOT_LOAD と同じ形。保存できた Being ごと
    SNAPSHOT_LOAD = "snapshot_load"
    # 名前を知らずに会った相手の名前を知った (#1581)。payload: learned_name /
    # appearance (それまでの呼び方) / how (「名乗り」か「呼びかけ」)。
    NAME_LEARNED = "name_learned"
    # 目次つきのエピソードを書き起こした (#1626)。1 回の書き起こしごとに 1 件。今は環境を離れるときだけ。
    # 2026-10-31 より前の trace には、今の短期記憶を畳んだときの trigger: compaction も残る (design_decisions D1824-21)。
    # payload: being_id / trigger (leaving。前の trace では compaction も) /
    # event_count (Being の短期記憶のまだまとめていない出来事の数。Being を引けないか失敗したときは None。
    # 2026-10-31 より前の trace では、今の短期記憶のまだ畳んでいない出来事の数。design_decisions D1824-23) /
    # awaited_until_turn (まだいきさつを待っている範囲の終わり。待っていなければ None。その範囲のエピソードは
    # 範囲が埋まったときに書くので、離れるときには書かない。being_episode_written と突き合わせて、終わりまでに
    # 記憶に入らなかった範囲を見つける。Being を引けたときだけ。2026-10-31 より前の trace には無い) /
    # skip_reason が no_events なのは、行になる出来事が無かったとき。結果の来ない 1 手だけなら event_count は 0 でない /
    # outcome (written / failed / skipped) / episode_count / dropped_count /
    # rewritten (outcome が written のときだけ。応答が崩れていて、同じ材料で書き直させて書けたか。
    # design_decisions D1626 の「その後」) /
    # written_turn / environment_name / episodes: list[{handle, summary,
    # recall_when, body_length, truncated: {鍵: 切り詰める前の長さ}}] /
    # 失敗なら error_type と error、飛ばしたなら skip_reason。
    EPISODE_WRITING = "episode_writing"
    # Being がエピソードを書き起こして記憶に加えた (エピソードの EpisodeWrittenEvent。#1824、design_decisions D1824-19)。
    # エピソードごとに 1 件。環境を離れるときの書き起こし (episode_writing) でも、短期記憶の
    # 範囲が埋まったときの書き起こしでも残る。範囲が埋まったときの書き起こしで 0 件だった範囲は、
    # being_short_term_memory_range_filled と突き合わせて見る (Being と、埋まったターン = written_turn が同じ)。
    # ほかの書き起こし (episode_writing。環境を離れるとき) のエピソードと、同じ Being・
    # 同じターンで重なることがある。重なったら episode_writing の件数を引いて見る。
    # payload: being_id / handle / environment_name / written_turn / summary / recall_when / body_length /
    # truncated ({鍵: 切り詰める前の長さ}。切り詰めなければ空。design_decisions D1824-20) /
    # rewritten (応答が崩れていて、同じ材料で書き直させて書いたエピソードか。design_decisions D1626 の「その後」)。
    BEING_EPISODE_WRITTEN = "being_episode_written"
    # Being の短期記憶の直近の範囲が埋まった (ShortTermMemoryRangeFilledEvent。#1824、design_decisions D1824-20)。
    # このあと、いきさつとエピソードが裏で書かれる。payload: being_id / turn (埋まったターン。その範囲で書いた
    # エピソードの written_turn と同じ) / until_turn (まとめる範囲の終わり) / experience_count (まとめる出来事の数)。
    BEING_SHORT_TERM_MEMORY_RANGE_FILLED = "being_short_term_memory_range_filled"
    # ゲームの出来事を、Being 側の短期記憶へ写さなかった (#1824、design_decisions D1824-7)。
    # 写さなかった 1 件ごとに 1 件。payload: being_id / source (observation / action_result /
    # move) / reason (being_inner_record / empty_body / missing_time_label / unpaired_result /
    # memory_rule / contract_violation / unexpected_error) / event_kind (観測の種類か道具の名前。無ければ None)。
    # unexpected_error なら error_type も持つ。
    BEING_SHORT_TERM_MEMORY_NOT_COPIED = "being_short_term_memory_not_copied"
    # recent_events_shadow_mismatch (design_decisions D1824-10) は 2026-10-31 より前の trace にだけある。
    # プロンプトを Being の短期記憶から作るようになって、比べるものが無くなった (design_decisions D1824-22)。
    # Being の短期記憶の直近の範囲が上限に届き、いきさつを待たずに古いターンを外した (#1824、design_decisions D1824-11)。
    # payload: being_id / turn (外したときのターン) / until_turn (外した範囲の終わり) / dropped_count (外した出来事の数)。
    BEING_SHORT_TERM_MEMORY_FOLD_FORCED = "being_short_term_memory_fold_forced"
    # Being の短期記憶に、裏で書いたいきさつが入った (短期記憶の ShortTermMemoryBackstoryAddedEvent。#1824、
    # design_decisions D1824-18)。書けなかったときと、同じか前の範囲までで短期記憶が断ったとき (design_decisions
    # D1824-17) は、これは残らず async_event_delivery_failed に残る。2026-10 より前の trace には、断ったときの
    # being_backstory_discarded が残っている。payload: being_id / until_turn / written_turn / flow / mood /
    # dropped_count (いきさつが入って外した出来事の数。上限で先に外していれば 0) /
    # truncated ({flow か mood: 切り詰める前の長さ}。切り詰めなければ空)。
    BEING_BACKSTORY_WRITTEN = "being_backstory_written"
    # エピソードの目次を 1 ターンのプロンプトに出した (#1623)。プロンプトを組むたびに 1 件。
    # payload: being_id / order (並べ方) / limit (N) / total_count (記録の件数) /
    # shown_handles (出した呼び名、出した順)。
    EPISODE_INDEX_SHOWN = "episode_index_shown"
    # エピソードを呼び出した (#1623)。呼び出しのツールの 1 回ごとに 1 件。
    # payload: being_id / outcome (recalled / rejected / failed) / requested (渡した呼び名) /
    # recalled なら turn と results: list[{handle, found, recall_count}]、
    # rejected なら reject_reason (malformed / too_many) と max_handles、
    # failed なら error_type と error。
    EPISODE_RECALL = "episode_recall"
    # エピソードの目次を直した (#1623)。目次を直すツールの 1 回ごとに 1 件。
    # payload: being_id / outcome (revised / rejected / failed) / handle /
    # revised なら turn・before と after ({about, recall_when})・truncated
    # ({鍵: 切り詰める前の長さ})、rejected なら reject_reason (malformed / unknown_handle)、
    # failed なら error_type と error。
    EPISODE_INDEX_REVISION = "episode_index_revision"
    SNAPSHOT_SAVE = "snapshot_save"
    # シナリオの round_assignment で player に割り当てた枠 (#1514)。宣言の無い
    # シナリオでは出ない。payload: round / seed / assignments: list[{player_id,
    # player_name, group_index, slot_index, spawn_spot, initial_state}]。
    # spawn_spot と initial_state は割り当てたあとに player が持つ値で、枠に
    # spawn_spot が無ければ宣言どおりの場所が入る。
    ROUND_ASSIGNMENT = "round_assignment"
    # teams のあるシナリオで、ゲームが終わったときのチームの勝敗と個人の結果
    # (#1516)。check_game_end で終わった tick に 1 件。teams の無いシナリオでは
    # 出ない。ゲームが終わる前に run が止まったとき (run_end の outcome が
    # TIMEOUT / LLM_ABORTED / INTERRUPTED) も出ない。勝敗は決まっていない。
    # payload: reason / teams: list[{team_id, name, result, satisfied, reason,
    # member_player_ids, member_player_string_ids}] / players: list[{player_id,
    # player_string_id, player_name, team_id, outcome, result}]。
    # result は WIN / LOSE / DRAW で、個人の result は所属チームと同じ。
    # outcome は PlayerOutcomeEnum の値 (寝返って脱出した人は RESCUED と LOSE)。
    TEAM_RESULT = "team_result"
    # Phase 9-1 (Issue #470): WorldStateSnapshot (= scenario 全体の world state)
    # の save / load。Being snapshot とは独立に発火 (= 同じ run で両方出る)。
    # WORLD_SNAPSHOT_LOAD payload:
    #   - directory: str
    #   - source_scenario: str (= snapshot 内に書かれていた scenario)
    #   - current_scenario: str (= 現 run の scenario)
    #   - world_tick: int (= restore 元の tick = 続きから start する tick)
    #   - restored_subsystems: list[str] (= 実際に codec が走った subsystem 名)
    # WORLD_SNAPSHOT_SAVE payload:
    #   - directory: str
    #   - source_scenario: str
    #   - world_tick: int (= save 時点の world tick)
    #   - captured_subsystems: list[str]
    WORLD_SNAPSHOT_LOAD = "world_snapshot_load"
    WORLD_SNAPSHOT_SAVE = "world_snapshot_save"
    # world flag の実際の状態遷移。SET_FLAG 等の効果が HIDDEN でも、
    # 作業進行の因果を後から検証できるように常時残す。同じ値への再設定は
    # 記録しない。payload: flag_name / set / source / actor_player_id。
    WORLD_FLAG_CHANGED = "world_flag_changed"
    # シナリオ述語を実際に1回評価した結果。未評価の policy skip は含めない。
    # payload: purpose / owner_id / owner_index / is_satisfied / reason_code /
    # root_condition_type / failed_condition_type / failed_path / missing_context /
    # probability_decisions
    SCENARIO_PREDICATE_EVALUATED = "scenario_predicate_evaluated"
    # 常時遠景の prompt 表示可視化。prompt build ごとに残す。
    # payload: spot_id / current_area_id / candidate_count / rendered_count /
    # rendered_area_ids / skipped_reasons / thresholds
    DISTANT_VIEW_RENDERED = "distant_view_rendered"
    DISTANT_VIEW_SKIPPED = "distant_view_skipped"
    # 動的遠景 cue の source 条件が false→true になった境界。
    # prompt build ごとの DISTANT_VIEW_* と違い、世界状態変化そのものを残す。
    # payload: cue_id / old_active / new_active / initialized_before /
    # origin_area_id / source_kind / source_state_key / visible_recipient_count /
    # delivery_skipped_reason
    DISTANT_CUE_STATE_CHANGED = "distant_cue_state_changed"
    # 動的遠景 cue の出現観測を player に配達した瞬間。
    # payload: cue_id / player_id / spot_id / direction / distance_band /
    # schedules_turn
    DISTANT_CUE_DELIVERED = "distant_cue_delivered"
    # reason-first 2段階ターン: 行動前評価を named tool_call で先に取り、
    # その評価を行動 tool 引数へ内部注入してから実行する経路の観測点。
    # STARTED: 2段階経路を開始した瞬間。
    # ASSESSED: step1 assess_situation が成立した瞬間。
    # ASSESSMENT_INJECTED: step1 主観フィールドを step2 行動引数へ注入した瞬間。
    # STEP_FAILED: step1 / step2 の契約違反で fail-fast した瞬間。
    # ACTION_SELECTED: step2 が実行可能な行動 tool を返した瞬間。
    REASON_FIRST_STARTED = "reason_first_started"
    REASON_FIRST_ASSESSED = "reason_first_assessed"
    REASON_FIRST_ASSESSMENT_INJECTED = "reason_first_assessment_injected"
    REASON_FIRST_STEP_FAILED = "reason_first_step_failed"
    REASON_FIRST_ACTION_SELECTED = "reason_first_action_selected"
    # 配信一元化リファクタ Stage 3X 前段 (観測): PipelineEventPublisher が
    # side handler の例外を握って observation pipeline を継続したとき、その失敗を
    # log だけでなく trace にも 1 件残す。現状は log のみで実 run の集計に乗らず、
    # 「load-bearing な同期副作用 (grace 登録/解除・消費効果適用) が実際にどれだけ
    # 失敗しているか」が見えない。将来 相①a を swallow→伝播へ変える判断の影響
    # 見積もりに使う。挙動は変えない (握って継続はそのまま、記録を足すだけ)。
    # payload:
    #   - handler: str (= 失敗した handler クラス名)
    #   - event_type: str (= 処理中だったドメインイベントのクラス名)
    #   - event_id: int | None (= イベント instance の event_id。二重失敗の集計用)
    #   - aggregate_type: str | None (= イベントの aggregate_type)
    #   - aggregate_id: int | str | None (= 影響対象の aggregate 識別子)
    #   - error_type: str (= 例外クラス名)
    #   - error_message: str (= 例外メッセージ。500 字超は切り詰め)
    # top-level player_id: aggregate が PlayerStatusAggregate のときだけ best-effort で
    # 入る (= どの player の grace 登録/解除・効果適用が失われたかの per-agent 分析用)。
    SIDE_HANDLER_FAILED = "side_handler_failed"
    # #1558: 世界の tick の段で、1 体 (プレイヤー / モンスター / 出来事 / 段そのもの)
    # の処理か、それに続く後処理が例外を出した。isolate ではその 1 体だけを取りやめて tick を続け、
    # fail_fast ではこれを残してから止める。run_end の world_tick_failure_counts と
    # report.md の件数は、この行の数と一致する。
    # payload:
    #   - stage: str (= 段の名前。"travel" / "monster_behavior" / "post_tick.llm_turn_trigger" など)
    #   - target_kind: str (= "player" | "monster" | "scenario_event" | "stage" など)
    #   - target_id: int | str | None
    #   - error_type / error_message (500 字超は切り詰め)
    #   - error_origin: str | None (= 例外が出た最も内側の "file:line in func")
    #   - committed: bool (= commit 後の後処理だけが失敗し、状態は確定済み)
    #   - continued: bool (= True は、確定済みの処理に続く後処理 (通知・観測・記録)
    #     の失敗で、取りやめるものが無く続けた。target_kind は失敗した後処理の種類)
    #   - policy: "isolate" | "fail_fast"
    WORLD_TICK_UNIT_FAILED = "world_tick_unit_failed"


@dataclass(frozen=True)
class TraceEvent:
    """トレース 1 件分。JSONL の 1 行に対応する。

    Attributes:
        seq: recorder 内で振られる単調増加シーケンス番号。同 tick 内の
            イベント並びを保つために使う。
        timestamp: ISO 8601 (UTC or naive local) 文字列。
        kind: ``TraceEventKind`` 参照のラベル。
        tick: ゲーム内 tick (該当しない場合は None)。
        player_id: 主体プレイヤー id (該当しない場合は None)。
        payload: kind ごとに定義する任意フィールド。JSON シリアライズ可能で
            あること。
    """

    seq: int
    timestamp: str
    kind: str
    tick: int | None = None
    player_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> dict[str, Any]:
        """json.dumps できる dict 形式に変換する。"""
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "kind": self.kind,
            "tick": self.tick,
            "player_id": self.player_id,
            "payload": dict(self.payload),
        }

    @staticmethod
    def from_jsonable(data: dict[str, Any]) -> TraceEvent:
        """``to_jsonable`` の逆変換。viewer 側で使う。"""
        if not isinstance(data, dict):
            raise TypeError("data must be dict")
        return TraceEvent(
            seq=int(data["seq"]),
            timestamp=str(data["timestamp"]),
            kind=str(data["kind"]),
            tick=data.get("tick"),
            player_id=data.get("player_id"),
            payload=dict(data.get("payload") or {}),
        )


__all__ = ["TraceEvent", "TraceEventKind"]
