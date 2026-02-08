from dataclasses import dataclass
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


@dataclass(frozen=True)
class WeatherChangedEvent(BaseDomainEvent[WeatherZoneId, str]):
    """天候が変化した際のイベント"""
    zone_id: WeatherZoneId
    old_weather: WeatherTypeEnum
    new_weather: WeatherTypeEnum
    intensity: float

    @classmethod
    def create(
        cls,
        aggregate_id: WeatherZoneId,
        aggregate_type: str,
        zone_id: WeatherZoneId,
        old_weather: WeatherTypeEnum,
        new_weather: WeatherTypeEnum,
        intensity: float
    ) -> "WeatherChangedEvent":
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            zone_id=zone_id,
            old_weather=old_weather,
            new_weather=new_weather,
            intensity=intensity
        )
