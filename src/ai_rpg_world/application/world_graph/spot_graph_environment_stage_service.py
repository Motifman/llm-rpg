from __future__ import annotations

import logging
import random
from typing import Callable, Optional, TYPE_CHECKING

from ai_rpg_world.application.common.exceptions import CommandPostCommitException

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.service.weather_simulation_service import (
    WeatherSimulationService,
)
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState

if TYPE_CHECKING:
    from ai_rpg_world.application.common.command_scope_factory import (
        CommandScopeFactoryPort,
    )


_logger = logging.getLogger(__name__)


class SpotGraphEnvironmentStageService:
    """Spot Graph 向けの軽量環境更新（現在は天候のみ）。"""

    def __init__(
        self,
        *,
        weather_state_provider: Callable[[], WeatherState],
        weather_state_setter: Callable[[WeatherState], None],
        update_interval_ticks: int = 6,
        on_weather_changed: Optional[Callable[[WeatherState], None]] = None,
        random_source: random.Random | None = None,
        command_scope_factory: "CommandScopeFactoryPort[object] | None" = None,
    ) -> None:
        self._weather_state_provider = weather_state_provider
        self._weather_state_setter = weather_state_setter
        self._update_interval_ticks = max(1, update_interval_ticks)
        self._on_weather_changed = on_weather_changed
        self._random = random_source or random.Random()
        self._command_scope_factory = command_scope_factory

    def set_weather_changed_callback(
        self,
        callback: Optional[Callable[[WeatherState], None]],
    ) -> None:
        self._on_weather_changed = callback

    def run(self, current_tick: WorldTick) -> None:
        if current_tick.value % self._update_interval_ticks != 0:
            return
        if self._command_scope_factory is not None:
            changed: WeatherState | None = None
            try:
                with self._command_scope_factory.create():
                    changed = self._advance_weather()
            except CommandPostCommitException:
                if changed is not None:
                    self._notify_weather_changed(changed)
                raise
            if changed is not None:
                self._notify_weather_changed(changed)
            return
        changed = self._advance_weather()
        self._notify_weather_changed(changed)

    def set_command_scope_factory(
        self,
        factory: "CommandScopeFactoryPort[object]",
    ) -> None:
        """本番stageを天候遷移1回の確定境界へ接続する。"""
        self._command_scope_factory = factory

    def rollback_snapshot(self) -> tuple[WeatherState, object]:
        """現天候と天候専用乱数位置を返す。"""
        return self._weather_state_provider(), self._random.getstate()

    def restore_rollback_snapshot(
        self,
        snapshot: tuple[WeatherState, object],
    ) -> None:
        """失敗した遷移の現天候と乱数位置を開始前へ戻す。"""
        weather_state, random_state = snapshot
        self._weather_state_setter(weather_state)
        self._random.setstate(random_state)

    def random_state(self) -> object:
        """snapshot codec向けに天候専用乱数位置を返す。"""
        return self._random.getstate()

    def restore_random_state(self, state: object) -> None:
        """検証済みの天候専用乱数位置を復元する。"""
        self._random.setstate(state)

    def _advance_weather(self) -> WeatherState:
        current = self._weather_state_provider()
        nxt = WeatherSimulationService.simulate_next_weather(
            current,
            random_source=self._random,
        )
        self._weather_state_setter(nxt)
        return nxt

    def _notify_weather_changed(self, weather_state: WeatherState) -> None:
        """確定済み天候を最善努力で通知する。"""
        if self._on_weather_changed is None:
            return
        try:
            self._on_weather_changed(weather_state)
        except Exception:  # noqa: BLE001 - 確定後観測は業務状態を戻さない
            _logger.warning(
                "weather callback failed after commit",
                exc_info=True,
            )
