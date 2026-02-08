from dataclasses import dataclass
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


from ai_rpg_world.domain.world.exception.weather_exception import WeatherIntensityValidationException


@dataclass(frozen=True)
class WeatherState:
    """現在の天候状態を表す値オブジェクト"""
    weather_type: WeatherTypeEnum
    intensity: float = 1.0  # 天候の強度（0.0 ~ 1.0）

    def __post_init__(self):
        if not (0.0 <= self.intensity <= 1.0):
            raise WeatherIntensityValidationException(f"Weather intensity must be between 0.0 and 1.0: {self.intensity}")

    @classmethod
    def clear(cls) -> "WeatherState":
        return cls(WeatherTypeEnum.CLEAR, 1.0)
