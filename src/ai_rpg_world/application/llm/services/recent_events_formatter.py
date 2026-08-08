"""直近の出来事（観測＋行動結果）をテキストに変換するデフォルト実装"""

from typing import List

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventEntry,
    UnifiedRecentEventLine,
    format_action_result_line_for_recent_events,
    format_observation_line_for_recent_events,
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IRecentEventsFormatter
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


class DefaultRecentEventsFormatter(IRecentEventsFormatter):
    """観測と行動結果を時刻でマージし、直近の出来事を時系列順（古い順）で 1 本テキストに変換する。

    entry に記録済みの ``game_time_label`` だけを描画する。描画時刻から
    「たった今 / さっき」等を再計算すると、一度追加した行が後のターンで
    書き換わり、直近の出来事を安定した接頭辞として扱えなくなるためである。
    世界内の絶対時刻なら、記録後も変わらず内容も嘘にならない。
    """

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
        return format_unified_timeline_as_recent_events_bullets(merged)

    def format_unified_entries(
        self, entries: List[UnifiedRecentEventEntry]
    ) -> str:
        """記録時に統一済みの時系列を、従来と同じ行規則で描画する。"""
        lines: list[UnifiedRecentEventLine] = []
        for entry in entries:
            if not isinstance(entry, UnifiedRecentEventEntry):
                raise TypeError(
                    "entries must contain only UnifiedRecentEventEntry"
                )
            text = (
                format_observation_line_for_recent_events(entry.payload)
                if entry.kind == "observation"
                else format_action_result_line_for_recent_events(entry.payload)
            )
            lines.append(
                UnifiedRecentEventLine(
                    occurred_at=entry.occurred_at,
                    kind=entry.kind,
                    text=text,
                )
            )
        return format_unified_timeline_as_recent_events_bullets(lines)
