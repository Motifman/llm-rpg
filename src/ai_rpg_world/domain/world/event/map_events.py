from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState


@dataclass(frozen=True)
class SpotWeatherChangedEvent(BaseDomainEvent[SpotId, str]):
    """スポットの天候が変化したイベント（屋外のみ・実際に変化した場合に発行）"""

    spot_id: SpotId
    old_weather_state: WeatherState
    new_weather_state: WeatherState
