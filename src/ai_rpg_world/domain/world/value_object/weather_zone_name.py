from dataclasses import dataclass
from ai_rpg_world.domain.world.exception.weather_exception import WeatherZoneNameValidationException


@dataclass(frozen=True)
class WeatherZoneName:
    """天候ゾーンの名前を表す値オブジェクト"""
    value: str

    def __post_init__(self):
        if not self.value or not self.value.strip():
            raise WeatherZoneNameValidationException("Weather zone name cannot be empty")

    def __str__(self) -> str:
        return self.value
