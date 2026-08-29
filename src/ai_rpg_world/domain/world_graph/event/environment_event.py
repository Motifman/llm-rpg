"""Spot Graphの環境stageが確定区間へ収集するイベント。"""

from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.value_object.time_of_day import TimeOfDay


@dataclass(frozen=True)
class SpotGraphWeatherChangedEvent(BaseDomainEvent[WorldTick, str]):
    """世界全体の天候が新しい状態へ遷移した。"""

    weather_state: WeatherState


@dataclass(frozen=True)
class SpotGraphDayNightPhaseChangedEvent(BaseDomainEvent[WorldTick, str]):
    """世界全体の昼夜フェーズが切り替わった。"""

    old_time: TimeOfDay
    new_time: TimeOfDay


__all__ = [
    "SpotGraphDayNightPhaseChangedEvent",
    "SpotGraphWeatherChangedEvent",
]
