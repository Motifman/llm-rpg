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
