"""直近の出来事（観測＋行動結果）をテキストに変換するデフォルト実装"""

from typing import List

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IRecentEventsFormatter
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


class DefaultRecentEventsFormatter(IRecentEventsFormatter):
    """観測と行動結果を時刻でマージし、直近の出来事を時系列順（古い順）で 1 本テキストに変換する。"""

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
