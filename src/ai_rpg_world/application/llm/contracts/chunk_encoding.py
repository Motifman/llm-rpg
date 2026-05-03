"""
チャンク単位のエピソードエンコード入力と、直近出来事の統一タイムライン（契約）。

RecentEventsFormatter と同じ行テキスト規則で観測・行動結果を occurred_at 昇順にマージする。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Sequence, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

UnifiedRecentEventKind = Literal["observation", "action_result"]

RECENT_EVENTS_EMPTY_PLACEHOLDER = "（直近の出来事はありません）"


def format_observation_line_for_recent_events(entry: ObservationEntry) -> str:
    """観測 1 件を直近出来事テキストの 1 行にする（game_time_label の付与規則はプロンプトと同一）。"""
    if not isinstance(entry, ObservationEntry):
        raise TypeError("entry must be ObservationEntry")
    text = entry.output.prose
    if entry.game_time_label:
        text = f"[{entry.game_time_label}] {text}"
    return text


def format_action_result_line_for_recent_events(entry: ActionResultEntry) -> str:
    """行動結果 1 件を直近出来事テキストの 1 行にする（成功・失敗の整形は RecentEventsFormatter と同一）。"""
    if not isinstance(entry, ActionResultEntry):
        raise TypeError("entry must be ActionResultEntry")
    if entry.success:
        return f"[行動] {entry.action_summary} → [結果] {entry.result_summary}"
    parts = [
        f"[行動] {entry.action_summary} → [失敗]",
        f"error_code={entry.error_code or '不明'}",
    ]
    if entry.tool_name:
        parts.append(f"tool={entry.tool_name}")
    if entry.should_reschedule:
        parts.append("次tick再試行の可能性あり")
    parts.append(entry.result_summary)
    return " | ".join(parts)


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
    merged.sort(key=lambda line: line.occurred_at, reverse=False)
    return tuple(merged)


def format_unified_timeline_as_recent_events_bullets(
    unified_timeline: Sequence[UnifiedRecentEventLine],
) -> str:
    """統一タイムラインを DefaultRecentEventsFormatter と同様の箇条書きテキストにする。"""
    if not unified_timeline:
        return RECENT_EVENTS_EMPTY_PLACEHOLDER
    return "\n".join(f"- {line.text}" for line in unified_timeline)


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
    )


def chunk_encoding_episode_generation_allowed(inp: ChunkEncodingInput) -> bool:
    """チャンク第 1 版: 区間に ActionResultEntry が 1 件以上あるときのみエピソード生成を起動してよい。"""
    if not isinstance(inp, ChunkEncodingInput):
        raise TypeError("inp must be ChunkEncodingInput")
    return len(inp.action_results) >= 1
