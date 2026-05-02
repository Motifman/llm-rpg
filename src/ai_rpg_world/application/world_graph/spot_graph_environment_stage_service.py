from __future__ import annotations

from typing import Callable, Optional

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.service.weather_simulation_service import (
    WeatherSimulationService,
)
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState


class SpotGraphEnvironmentStageService:
    """Spot Graph 向けの軽量環境更新（現在は天候のみ）。"""

    def __init__(
        self,
        *,
        weather_state_provider: Callable[[], WeatherState],
        weather_state_setter: Callable[[WeatherState], None],
        update_interval_ticks: int = 6,
        on_weather_changed: Optional[Callable[[WeatherState], None]] = None,
    ) -> None:
        self._weather_state_provider = weather_state_provider
        self._weather_state_setter = weather_state_setter
        self._update_interval_ticks = max(1, update_interval_ticks)
        self._on_weather_changed = on_weather_changed

    def set_weather_changed_callback(
        self,
        callback: Optional[Callable[[WeatherState], None]],
    ) -> None:
        self._on_weather_changed = callback

    def run(self, current_tick: WorldTick) -> None:
        if current_tick.value % self._update_interval_ticks != 0:
            return
        current = self._weather_state_provider()
        nxt = WeatherSimulationService.simulate_next_weather(current)
        self._weather_state_setter(nxt)
        if self._on_weather_changed is not None:
            self._on_weather_changed(nxt)
