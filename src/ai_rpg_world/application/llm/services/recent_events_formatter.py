"""直近の出来事（観測＋行動結果）をテキストに変換するデフォルト実装"""

from typing import List

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IRecentEventsFormatter
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


def _merge_by_time(
    observations: List[ObservationEntry],
    action_results: List[ActionResultEntry],
) -> List[tuple]:
    """
    観測と行動結果を occurred_at でマージし、(occurred_at, kind, text) のリストを新しい順で返す。
    kind: "observation" | "action_result"
    """
    merged: List[tuple] = []
    for e in observations:
        merged.append((e.occurred_at, "observation", e.output.prose))
    for e in action_results:
        text = f"[行動] {e.action_summary} → [結果] {e.result_summary}"
        merged.append((e.occurred_at, "action_result", text))
    merged.sort(key=lambda x: x[0], reverse=True)
    return merged


class DefaultRecentEventsFormatter(IRecentEventsFormatter):
    """観測と行動結果を時刻でマージし、直近の出来事の 1 本テキストに変換する。"""

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

        merged = _merge_by_time(observations, action_results)
        if not merged:
            return "（直近の出来事はありません）"
        lines = [f"- {item[2]}" for item in merged]
        return "\n".join(lines)
