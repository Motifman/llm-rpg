"""天候変化の観測文を作る。"""

from typing import Any

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import (
    SpotWeatherChangedEvent,
)


class WorldObservationFormatter:
    """SpotWeatherChangedEvent の観測文を作る。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> ObservationOutput | None:
        if isinstance(event, SpotWeatherChangedEvent):
            return self._format_spot_weather_changed(event, recipient_player_id)
        return None

    def _format_spot_weather_changed(
        self, event: SpotWeatherChangedEvent, recipient_id: PlayerId
    ) -> ObservationOutput | None:
        old_s = event.old_weather_state.weather_type.value
        new_s = event.new_weather_state.weather_type.value
        prose = f"天気が{old_s}から{new_s}に変わりました。"
        structured: dict[str, Any] = {
            "type": "weather_changed",
            "old": old_s,
            "new": new_s,
            "spot_id_value": event.spot_id.value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="environment",
            schedules_turn=True,
        )
