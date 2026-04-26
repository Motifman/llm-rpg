"""直近の出来事（観測＋行動結果）をテキストに変換するデフォルト実装"""

from typing import List

from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.contracts.interfaces import IRecentEventsFormatter
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry


def _format_action_result_line(entry: ActionResultEntry) -> str:
    if entry.success:
        return f"[行動] {entry.action_summary} → [結果] {entry.result_summary}"
    parts = [f"[行動] {entry.action_summary} → [失敗]", f"error_code={entry.error_code or '不明'}"]
    if entry.tool_name:
        parts.append(f"tool={entry.tool_name}")
    if entry.should_reschedule:
        parts.append("次tick再試行の可能性あり")
    parts.append(entry.result_summary)
    return " | ".join(parts)


def _merge_by_time(
    observations: List[ObservationEntry],
    action_results: List[ActionResultEntry],
) -> List[tuple]:
    """
    観測と行動結果を occurred_at でマージし、(occurred_at, kind, text) のリストを時系列順（古い順）で返す。
    キャッシュ効率とLLMの出力位置重視のため、新しい情報が末尾に来るようにする。
    kind: "observation" | "action_result"
    観測には game_time_label があれば "[ラベル] 観測文" とする。
    """
    merged: List[tuple] = []
    for e in observations:
        text = e.output.prose
        if e.game_time_label:
            text = f"[{e.game_time_label}] {text}"
        merged.append((e.occurred_at, "observation", text))
    for e in action_results:
        text = _format_action_result_line(e)
        merged.append((e.occurred_at, "action_result", text))
    merged.sort(key=lambda x: x[0], reverse=False)
    return merged


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

        merged = _merge_by_time(observations, action_results)
        if not merged:
            return "（直近の出来事はありません）"
        lines = [f"- {item[2]}" for item in merged]
        return "\n".join(lines)
