"""直近の出来事（観測＋行動結果）をテキストに変換するデフォルト実装"""

from datetime import datetime
from typing import Callable, List, Optional

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    RECENT_EVENTS_EMPTY_PLACEHOLDER,
    UnifiedRecentEventLine,
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IRecentEventsFormatter
from ai_rpg_world.application.llm.services.subjective_time import (
    subjective_time_label,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


class DefaultRecentEventsFormatter(IRecentEventsFormatter):
    """観測と行動結果を時刻でマージし、直近の出来事を時系列順（古い順）で 1 本テキストに変換する。

    Issue #526 後続 (主観時間 v0): ``time_provider`` を注入すると、各 entry
    の ``occurred_at`` から「昨日 / 数分前」等の主観時間ラベルを計算して
    行の先頭に prepend する。未注入 (= None) なら従来挙動を完全維持。

    注: chunk encoding (= episode 永続化) 経路はこの formatter を経由せず、
    ``merge_observations_and_action_results_to_unified_timeline`` を直接
    使う。chunk に主観時間ラベルは入らないため、episode が「昨日」の
    まま固まる問題は発生しない。
    """

    def __init__(
        self,
        *,
        time_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if time_provider is not None and not callable(time_provider):
            raise TypeError("time_provider must be callable or None")
        self._time_provider = time_provider

    def format(
        self,
        observations: List[ObservationEntry],
        action_results: List[ActionResultEntry],
    ) -> str:
        if not isinstance(observations, list):
            raise TypeError("observations must be list")
        if not isinstance(action_results, list):
            raise TypeError("action_results must be list")
        for o in observations:
            if not isinstance(o, ObservationEntry):
                raise TypeError("observations must contain only ObservationEntry")
        for a in action_results:
            if not isinstance(a, ActionResultEntry):
                raise TypeError("action_results must contain only ActionResultEntry")

        merged = merge_observations_and_action_results_to_unified_timeline(
            observations, action_results
        )
        if self._time_provider is None:
            return format_unified_timeline_as_recent_events_bullets(merged)
        # 主観時間ラベル付き整形
        return _format_unified_timeline_with_subjective_time(
            merged, self._time_provider()
        )


def _format_unified_timeline_with_subjective_time(
    unified_timeline: tuple[UnifiedRecentEventLine, ...] | list[UnifiedRecentEventLine],
    now: datetime,
) -> str:
    """各行の先頭に ``[<主観時間ラベル>]`` を prepend して bullets を返す。

    既存の ``[game_time_label] ...`` がある行はその前に挿入される
    (= ``[昨日] [Day 1 朝] テキスト``)。語彙が冗長になる場合の縮約は
    v0 では行わない (= 単純結合)。
    """
    if not unified_timeline:
        return RECENT_EVENTS_EMPTY_PLACEHOLDER
    lines: list[str] = []
    for line in unified_timeline:
        label = subjective_time_label(now, line.occurred_at)
        if label is None:
            lines.append(f"- {line.text}")
        else:
            lines.append(f"- [{label}] {line.text}")
    return "\n".join(lines)
