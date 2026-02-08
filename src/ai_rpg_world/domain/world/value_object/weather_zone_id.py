from dataclasses import dataclass
import uuid


from ai_rpg_world.domain.world.exception.weather_exception import WeatherZoneIdValidationException


@dataclass(frozen=True)
class WeatherZoneId:
    """天候ゾーンの一意識別子"""
    value: str

    def __post_init__(self):
        if not self.value or not self.value.strip():
            raise WeatherZoneIdValidationException("WeatherZoneId cannot be empty")

    @classmethod
    def generate(cls) -> "WeatherZoneId":
        return cls(str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value
