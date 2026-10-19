"""
直近出来事の統一タイムライン（契約）。

RecentEventsFormatter と同じ行テキスト規則で観測・行動結果を occurred_at 昇順にマージする。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    format_action_call_for_history,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry

UnifiedRecentEventKind = Literal["observation", "action_result"]

RECENT_EVENTS_EMPTY_PLACEHOLDER = "（直近の出来事はありません）"


@dataclass(frozen=True)
class UnifiedRecentEventEntry:
    """記録時から観測と行動結果を同じ時系列に置くタグ付き共用体。"""

    occurred_at: datetime
    game_time_label: str | None
    kind: UnifiedRecentEventKind
    payload: ObservationEntry | ActionResultEntry

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
    def from_observation(cls, entry: ObservationEntry) -> UnifiedRecentEventEntry:
        return cls(
            occurred_at=entry.occurred_at,
            game_time_label=entry.game_time_label,
            kind="observation",
            payload=entry,
        )

    @classmethod
    def from_action_result(
        cls, entry: ActionResultEntry
    ) -> UnifiedRecentEventEntry:
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
            return f"{time_prefix}[行動] {entry.action_summary}{continuation_lines}"
        if entry.tool_name == TOOL_NAME_SPEECH and entry.result_summary:
            return (
                f"{time_prefix}[行動] {entry.action_summary}"
                f"{entry.result_summary}{continuation_lines}"
            )
        return (
            f"{time_prefix}[行動] {entry.action_summary} → [結果] {entry.result_summary}"
            f"{continuation_lines}"
        )
    parts = [f"{time_prefix}[行動] {entry.action_summary} → [失敗]"]
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
) -> tuple[UnifiedRecentEventLine, ...]:
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
    for ar in action_results:
        if not isinstance(ar, ActionResultEntry):
            raise TypeError("action_results must contain only ActionResultEntry")
        merged.append(
            UnifiedRecentEventLine(
                occurred_at=ar.occurred_at,
                kind="action_result",
                text=format_action_result_line_for_recent_events(ar),
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
