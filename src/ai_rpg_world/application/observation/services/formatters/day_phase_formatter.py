"""昼夜フェーズ遷移イベントの観測フォーマッター。

DayPhaseChangedEvent から「{display_text} になった」という environment カテゴリの
プローズを生成する。表示テキストはイベントに display_text が乗っているため、
formatter 側でフェーズ名のハードコード辞書は持たない。
"""

from __future__ import annotations

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    DayPhaseChangedEvent,
)


class DayPhaseObservationFormatter:
    """DayPhaseChangedEvent を environment カテゴリ観測に変換する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if not isinstance(event, DayPhaseChangedEvent):
            return None

        prose = f"{event.to_phase_display_text}になった。"
        if event.is_dark:
            prose += "あたりは暗くなりつつある。"

        structured = {
            "type": "day_phase_changed",
            "from_phase": event.from_phase_name,
            "to_phase": event.to_phase_name,
            "ambient_light": event.ambient_light,
            "is_dark": event.is_dark,
        }

        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=False,
            breaks_movement=False,
        )
