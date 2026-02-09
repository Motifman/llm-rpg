from dataclasses import dataclass
from typing import Union


from ai_rpg_world.domain.world.exception.weather_exception import WeatherZoneIdValidationException


@dataclass(frozen=True)
class WeatherZoneId:
    """天候ゾーンの一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise WeatherZoneIdValidationException(f"WeatherZone ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "WeatherZoneId":
        """intまたはstrからWeatherZoneIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise WeatherZoneIdValidationException(f"Invalid WeatherZone ID format (must be an integer): {value}")
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
