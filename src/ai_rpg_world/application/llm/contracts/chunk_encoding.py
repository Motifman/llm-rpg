"""
チャンク単位のエピソードエンコード入力と、直近出来事の統一タイムライン（契約）。

RecentEventsFormatter と同じ行テキスト規則で観測・行動結果を occurred_at 昇順にマージする。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence, Tuple, Union

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    format_action_call_for_history,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

UnifiedRecentEventKind = Literal["observation", "action_result"]

RECENT_EVENTS_EMPTY_PLACEHOLDER = "（直近の出来事はありません）"


@dataclass(frozen=True)
class UnifiedRecentEventEntry:
    """記録時から観測と行動結果を同じ時系列に置くタグ付き共用体。"""

    occurred_at: datetime
    game_time_label: str | None
    kind: UnifiedRecentEventKind
    payload: Union[ObservationEntry, ActionResultEntry]

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if self.kind not in ("observation", "action_result"):
            raise TypeError("kind must be 'observation' or 'action_result'")
        expected_type = (
            ObservationEntry if self.kind == "observation" else ActionResultEntry
        )
        if not isinstance(self.payload, expected_type):
            raise TypeError(f"payload does not match kind={self.kind!r}")
        if self.occurred_at != self.payload.occurred_at:
            raise ValueError("outer occurred_at must match payload.occurred_at")
        if self.game_time_label != self.payload.game_time_label:
            raise ValueError(
                "outer game_time_label must match payload.game_time_label"
            )

    @classmethod
    def from_observation(cls, entry: ObservationEntry) -> "UnifiedRecentEventEntry":
        return cls(
            occurred_at=entry.occurred_at,
            game_time_label=entry.game_time_label,
            kind="observation",
            payload=entry,
        )

    @classmethod
    def from_action_result(
        cls, entry: ActionResultEntry
    ) -> "UnifiedRecentEventEntry":
        return cls(
            occurred_at=entry.occurred_at,
            game_time_label=entry.game_time_label,
            kind="action_result",
            payload=entry,
        )


def format_observation_line_for_recent_events(entry: ObservationEntry) -> str:
    """観測 1 件を直近出来事テキストの 1 行にする。

    prose が空の観測は structured を分析用に保持しつつ、時刻だけの空行を
    prompt へ作らないよう空文字のまま返す。
    """
    if not isinstance(entry, ObservationEntry):
        raise TypeError("entry must be ObservationEntry")
    text = entry.output.prose
    if not text.strip():
        return ""
    if entry.game_time_label:
        text = f"[{entry.game_time_label}] {text}"
    return text


def format_action_result_line_for_recent_events(entry: ActionResultEntry) -> str:
    """行動結果 1 件を直近出来事テキストの 1 行にする（成功・失敗の整形は RecentEventsFormatter と同一）。

    Issue #188 改善:
    - ``game_time_label`` があれば観測と同じ ``[時刻] ...`` 形式で先頭に prefix。
    - ``omit_result_in_prompt=True`` の成功時は ``→ [結果] ...`` を省略し、
      ``[行動] {action_summary}`` だけにする (speech_say の「発言しました。」
      のような自明な結果のノイズ削減)。失敗時は省略しない (LLM 学習用)。

    成功した行動には ``呼び出し:`` の続き行を置く。引用符つきの値だけが
    そのまま tool 引数へ写せる値で、自由文は引用符なしの日本語
    プレースホルダで示す。通常の失敗時は通らなかった値を手本として残さず、
    ``error_code`` と復帰文だけを学習材料にする。世界の外側で起きた失敗は
    ``error_code=None`` として記録され、診断ラベルを補わず世界内の文だけを出す。
    """
    if not isinstance(entry, ActionResultEntry):
        raise TypeError("entry must be ActionResultEntry")
    time_prefix = f"[{entry.game_time_label}] " if entry.game_time_label else ""
    # #552 PR-A: 行動前の予測 (expected_result) を [予測: ...] として行内に別表記する。
    # action_summary の JSON からは sanitizer で落としてあるので二重表示にならない。
    # 構造化フィールドから読むので、予測が無ければ何も足さない。「行動 → 予測 → 結果」
    # の順で並べ、失敗 / omit_result 行にも付ける (予測と実際のズレを読み取れるように)。
    prediction = (entry.expected_result or "").strip()
    prediction_label = f" [予測: {prediction}]" if prediction else ""
    inner_thought = (entry.inner_thought or "").strip()
    inner_thought_line = f"\n  心の声: {inner_thought}" if inner_thought else ""
    if entry.success:
        # **発話だけは呼び出し行を置かない。** 本文は伏せ字になるので
        # ``speak(content=本文)`` としか書けず、直前の行が「あなたは言った」と
        # 言っている以上、**情報が 1 文字も増えない**。手本としても働かない
        # (伏せ字を真似しても意味がない)。他のツールは引数が具体値なので残す。
        call_line = (
            ""
            if entry.tool_name == TOOL_NAME_SPEECH
            else "\n  呼び出し: " + format_action_call_for_history(
                entry.tool_name,
                entry.identifier_arguments,
                entry.free_text_argument_names,
            )
        )
        continuation_lines = call_line + inner_thought_line
        if entry.omit_result_in_prompt:
            return f"{time_prefix}[行動] {entry.action_summary}{prediction_label}{continuation_lines}"
        if entry.tool_name == TOOL_NAME_SPEECH and entry.result_summary:
            return (
                f"{time_prefix}[行動] {entry.action_summary}{prediction_label}"
                f"{entry.result_summary}{continuation_lines}"
            )
        return (
            f"{time_prefix}[行動] {entry.action_summary}{prediction_label} → [結果] {entry.result_summary}"
            f"{continuation_lines}"
        )
    parts = [f"{time_prefix}[行動] {entry.action_summary}{prediction_label} → [失敗]"]
    if entry.error_code is not None:
        parts.append(f"error_code={entry.error_code}")
        if entry.tool_name:
            parts.append(f"tool={entry.tool_name}")
        if entry.should_reschedule:
            parts.append("次tick再試行の可能性あり")
    parts.append(entry.result_summary)
    return " | ".join(parts) + inner_thought_line


@dataclass(frozen=True)
class UnifiedRecentEventLine:
    """観測または行動結果の 1 行。occurred_at 昇順で並べる。"""

    occurred_at: datetime
    kind: UnifiedRecentEventKind
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.occurred_at, datetime):
            raise TypeError("occurred_at must be datetime")
        if self.kind not in ("observation", "action_result"):
            raise TypeError("kind must be 'observation' or 'action_result'")
        if not isinstance(self.text, str):
            raise TypeError("text must be str")


def merge_observations_and_action_results_to_unified_timeline(
    observations: Sequence[ObservationEntry],
    action_results: Sequence[ActionResultEntry],
) -> Tuple[UnifiedRecentEventLine, ...]:
    """
    観測と行動結果を occurred_at 昇順にマージした統一タイムラインを返す。
    各行の text は DefaultRecentEventsFormatter と同一規則。
    """
    merged: list[UnifiedRecentEventLine] = []
    for e in observations:
        if not isinstance(e, ObservationEntry):
            raise TypeError("observations must contain only ObservationEntry")
        merged.append(
            UnifiedRecentEventLine(
                occurred_at=e.occurred_at,
                kind="observation",
                text=format_observation_line_for_recent_events(e),
            )
        )
    for e in action_results:
        if not isinstance(e, ActionResultEntry):
            raise TypeError("action_results must contain only ActionResultEntry")
        merged.append(
            UnifiedRecentEventLine(
                occurred_at=e.occurred_at,
                kind="action_result",
                text=format_action_result_line_for_recent_events(e),
            )
        )
    merged.sort(key=lambda line: line.occurred_at.timestamp(), reverse=False)
    return tuple(merged)


def format_unified_timeline_as_recent_events_bullets(
    unified_timeline: Sequence[UnifiedRecentEventLine],
) -> str:
    """統一タイムラインを DefaultRecentEventsFormatter と同様の箇条書きテキストにする。"""
    visible_lines = [line for line in unified_timeline if line.text.strip()]
    if not visible_lines:
        return RECENT_EVENTS_EMPTY_PLACEHOLDER
    return "\n".join(f"- {line.text}" for line in visible_lines)


@dataclass(frozen=True)
class ChunkEncodingInput:
    """
    チャンク 1 回分のエンコード入力（不変）。
    unified_timeline は observations と action_results をマージした結果と一致すること。
    """

    player_id: PlayerId
    observations: Tuple[ObservationEntry, ...]
    action_results: Tuple[ActionResultEntry, ...]
    unified_timeline: Tuple[UnifiedRecentEventLine, ...]
    observation_overflow_from_window: Tuple[ObservationEntry, ...] = ()
    # U10b (予測誤差統一設計 部品6・pending prediction 清算): この chunk を
    # 補完する時点で being が保持している「窓が開いた約束」(tick_from に達した
    # pending) の一覧。chunk 主観補完 LLM に「これらは果たされたか」を判定
    # させるためにプロンプトへ載せる。coordinator が close 判定時に注入する
    # (flag OFF / store 未配線なら常に空 = 導入前と byte 一致)。
    active_pending_predictions: Tuple[PendingPrediction, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be tuple[ObservationEntry, ...]")
        if not isinstance(self.action_results, tuple):
            raise TypeError("action_results must be tuple[ActionResultEntry, ...]")
        if not isinstance(self.unified_timeline, tuple):
            raise TypeError("unified_timeline must be tuple[UnifiedRecentEventLine, ...]")
        if not isinstance(self.observation_overflow_from_window, tuple):
            raise TypeError("observation_overflow_from_window must be tuple[ObservationEntry, ...]")
        for idx, o in enumerate(self.observations):
            if not isinstance(o, ObservationEntry):
                raise TypeError(f"observations[{idx}] must be ObservationEntry")
        for idx, a in enumerate(self.action_results):
            if not isinstance(a, ActionResultEntry):
                raise TypeError(f"action_results[{idx}] must be ActionResultEntry")
        for idx, line in enumerate(self.unified_timeline):
            if not isinstance(line, UnifiedRecentEventLine):
                raise TypeError(f"unified_timeline[{idx}] must be UnifiedRecentEventLine")
        for idx, o in enumerate(self.observation_overflow_from_window):
            if not isinstance(o, ObservationEntry):
                raise TypeError(f"observation_overflow_from_window[{idx}] must be ObservationEntry")
        if not isinstance(self.active_pending_predictions, tuple):
            raise TypeError("active_pending_predictions must be tuple[PendingPrediction, ...]")
        for idx, p in enumerate(self.active_pending_predictions):
            if not isinstance(p, PendingPrediction):
                raise TypeError(f"active_pending_predictions[{idx}] must be PendingPrediction")
        expected = merge_observations_and_action_results_to_unified_timeline(
            self.observations, self.action_results
        )
        if expected != self.unified_timeline:
            raise ValueError(
                "unified_timeline must equal merge of observations and action_results"
            )


def build_chunk_encoding_input(
    player_id: PlayerId,
    observations: Sequence[ObservationEntry],
    action_results: Sequence[ActionResultEntry],
    *,
    observation_overflow_from_window: Sequence[ObservationEntry] = (),
    active_pending_predictions: Sequence[PendingPrediction] = (),
) -> ChunkEncodingInput:
    """観測スライス・行動結果スライスから ChunkEncodingInput を組み立てる。"""
    if not isinstance(player_id, PlayerId):
        raise TypeError("player_id must be PlayerId")
    obs_t = tuple(observations)
    act_t = tuple(action_results)
    timeline = merge_observations_and_action_results_to_unified_timeline(obs_t, act_t)
    return ChunkEncodingInput(
        player_id=player_id,
        observations=obs_t,
        action_results=act_t,
        unified_timeline=timeline,
        observation_overflow_from_window=tuple(observation_overflow_from_window),
        active_pending_predictions=tuple(active_pending_predictions),
    )


def chunk_encoding_episode_generation_allowed(inp: ChunkEncodingInput) -> bool:
    """チャンク第 1 版: 区間に ActionResultEntry が 1 件以上あるときのみエピソード生成を起動してよい。"""
    if not isinstance(inp, ChunkEncodingInput):
        raise TypeError("inp must be ChunkEncodingInput")
    return len(inp.action_results) >= 1
