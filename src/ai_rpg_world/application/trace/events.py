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
from typing import Any, Dict, Optional


class TraceEventKind:
    """``TraceEvent.kind`` に入れる文字列定数群。

    enum にしないのは、後から外部スクリプトが新しい kind を勝手に流す自由を
    残すため (JSONL なので緩く)。よく使う既知値だけここに集める。
    """

    RUN_START = "run_start"
    RUN_END = "run_end"
    TICK_START = "tick_start"
    TICK_END = "tick_end"
    OBSERVATION = "observation"
    ACTION = "action"
    ACTION_RESULT = "action_result"
    MEMO_ADD = "memo_add"
    MEMO_DONE = "memo_done"
    MEMO_HINT = "memo_hint"
    # Issue #240 後続: 同一 (tool, fingerprint) の連打を loop guard が検知し
    # 警告観測を注入したタイミング。trace で wait spam の抑制動作を可視化する。
    # payload: tool_name / argument_fingerprint / consecutive_count
    LOOP_GUARD_WARNING = "loop_guard_warning"
    SCENE = "scene"
    NOTE = "note"
    # Phase 1d viewer: プレイヤーがスポット間を移動した瞬間。空間アニメーション
    # 描画に使う。payload は ``from_spot_id`` / ``to_spot_id`` / ``spot_name`` /
    # ``player_name`` を持つ (run の最初の初期配置は from_spot_id=None で emit)。
    POSITION_CHANGE = "position_change"
    # Issue #283 後続: episodic memory pipeline の可視化。
    # EPISODIC_CHUNK_WRITTEN: ``EpisodicChunkCoordinator`` が境界を閉じて
    # SubjectiveEpisode を 1 件 store に書いた瞬間。
    # payload: episode_id / boundary_reason / cues (canonical list) /
    # recall_text_snippet / action_count / observation_count
    EPISODIC_CHUNK_WRITTEN = "episodic_chunk_written"
    # EPISODIC_RECALL: ``DefaultPromptBuilder._run_passive_recall`` が
    # passive recall を実行した瞬間。
    # payload: situation_cues (canonical list) / candidate_count /
    # candidates (episode_id / source_axes / recall_text_snippet)
    EPISODIC_RECALL = "episodic_recall"
    # Issue #295 後続 (PR #309): episodic subjective LLM 補完を非同期で実行する
    # スケジューラ (``ThreadPoolEpisodicSubjectiveScheduler`` 等) が、
    # LLM 呼び出しを完了して store に「リッチ化された」episode を上書きした瞬間。
    # payload: episode_id / latency_ms / recall_text_snippet
    EPISODIC_SUBJECTIVE_FILLED = "episodic_subjective_filled"
    # スケジューラが LLM 呼び出しを試みたが失敗 (LLM API エラー / parse 失敗 等)
    # → draft (= テンプレ既定値) のまま store に残った瞬間。
    # payload: episode_id / error_code (LLM_API_CALL_FAILED 等)
    EPISODIC_SUBJECTIVE_FAILED = "episodic_subjective_failed"
    # キュー満杯で enqueue を諦めた瞬間 (back-pressure)。
    # payload: episode_id / queue_size / max_queue_size
    EPISODIC_SUBJECTIVE_DROPPED = "episodic_subjective_dropped"
    # LLM 性能メトリクス (実験 #356 後続): Phase A の LLM 呼び出し 1 件分の
    # 壁時計 latency / token usage / TPS を記録する。
    # payload: model / wall_latency_ms / prompt_tokens / completion_tokens /
    # cached_tokens / tps / success / error_code / cost_usd
    # ``cost_usd`` は OpenRouter 経由時のみ provider 宣告値が乗る (直結 / vLLM では 0.0)。
    # τ_sim の設定根拠データ + scenario ごとの cost 評価に使う。
    LLM_CALL = "llm_call"
    # prompt section の文字数内訳 (実験 #356 後続: prefix cache 分析用)。
    # prompt_builder.build() が messages / tools を組み上げた直後に 1 件記録する。
    # payload: system_chars / objective_chars / current_state_chars / memos_chars /
    # prediction_feedback_chars / recent_events_chars / recall_chars / inventory_chars /
    # instruction_chars / tools_chars / messages_total_chars
    # token 数ではなく char 数で出す: 軽量 / モデル非依存 / deterministic。
    # 分析側で同 turn の prompt_tokens 比に換算する (≒ token 内訳)。
    PROMPT_SECTION_BREAKDOWN = "prompt_section_breakdown"
    # Phase 1c: semantic memory passive top-K の発火結果。prompt build 時に
    # ``SemanticPassiveRecallService.retrieve`` が走ったタイミングで 1 件記録。
    # payload: situation_cues / top_k / candidate_count / candidates[].entry_id /
    # candidates[].score / .recency / .importance / .relevance / .text_snippet /
    # .tags / .importance_score
    # 検証中は top_k=0 (default) で発火しない。SEMANTIC_PASSIVE_TOP_K env で
    # 明示的に有効化したときだけ trace に出る。
    SEMANTIC_PASSIVE_RECALL = "semantic_passive_recall"
    # Phase 2.1: 短期記憶 L4 生成タスクが scheduler でキュー満杯 / shutdown 後に
    # drop された瞬間。payload: reason / queue_size / max_queue_size。
    # silent failure 防止のため、drop は trace + warning で必ず可観測化する。
    SHORT_TERM_SUMMARY_DROPPED = "short_term_summary_dropped"
    # Phase 2.2: 短期記憶 L4 生成タスク (scheduler worker 内) が例外で死んだ瞬間。
    # 通常パスでは ``_run_generation`` が全例外を握って template fallback を
    # install するため、ここに到達するのは "fallback すら失敗した" バグ性の
    # 事象。log だけでなく trace でも見えるようにする (silent failure 防止)。
    # payload: error_type / error_message_snippet / latency_ms (worker 開始からの)
    SHORT_TERM_SUMMARY_GENERATION_FAILED = "short_term_summary_generation_failed"
    # PR #435: L4 mid summary が install された瞬間 (LLM 成功 / template fallback
    # の両方を含む)。失敗時の trace は既に SHORT_TERM_SUMMARY_DROPPED /
    # _GENERATION_FAILED にあるが、**成功時の生成内容** を捕捉する経路が無く、
    # 「rolling が何を圧縮して覚えていたか」が事後追えなかった (実験 #30 前準備で
    # ギャップとして発覚)。
    # payload: summary_id / raw_count / compressed_activity / emotional_summary /
    # unresolved / is_fallback
    SHORT_TERM_SUMMARY_GENERATED = "short_term_summary_generated"
    # PR #435: L5 long summary が install された瞬間 (LLM 成功 / template fallback
    # / previous_l5 延命を含む)。Phase 3 で生成される self_image / world_view を
    # 後から振り返るための trace。生成タイミング + 内容を 1 件で残す。
    # payload: summary_id / generation_index / self_image / world_view / is_fallback
    SHORT_TERM_LONG_SUMMARY_GENERATED = "short_term_long_summary_generated"
    # Phase 7 (Issue #470): Being snapshot save / load。run が前回 snapshot
    # からの続きか・どの player の memory が今 run の trace に乗っているかを
    # post-hoc 分析できるようにする。silent failure 防止用に **必ず** trace に
    # 1 件残す (= load 成功 / 失敗、save 成功 / 失敗いずれの場合も)。
    # SNAPSHOT_LOAD payload:
    #   - directory: str (= --snapshot-load-dir)
    #   - restored_count: int (= 成功した Being 数)
    #   - source_scenario: str | None (= snapshot 内に書かれていた元シナリオ名。
    #     現 scenario と異なる場合は cross-scenario transfer)
    # SNAPSHOT_SAVE payload:
    #   - directory: str (= --snapshot-save-dir)
    #   - succeeded_count: int
    #   - failed_count: int
    #   - failures: list[{being_id, error}]
    SNAPSHOT_LOAD = "snapshot_load"
    SNAPSHOT_SAVE = "snapshot_save"
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
    # U2 (証拠台帳統一設計): chunk 主観補完が prediction_error を非 None で
    # 埋めた瞬間、ルールベースの転記で BeliefEvidence 1 件を evidence buffer
    # に積んだタイミング。学習の素材がどれだけ流れているかを観測するための
    # trace (M1 マイルストーンで流量を確認する)。semantic の想起挙動は
    # 変えない (buffer に積むだけ)。
    # payload: evidence_id / source_kind / episode_ids / cue_signature /
    # text_snippet / salience
    BELIEF_EVIDENCE = "belief_evidence"


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
    tick: Optional[int] = None
    player_id: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_jsonable(self) -> Dict[str, Any]:
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
    def from_jsonable(data: Dict[str, Any]) -> "TraceEvent":
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
