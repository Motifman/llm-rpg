"""スポーン・リスポーン条件を表す値オブジェクト"""

from dataclasses import dataclass
from typing import Optional, Set, FrozenSet

from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum


@dataclass(frozen=True)
class SpawnCondition:
    """
    スポーン／リスポーンを実行する条件。
    時間帯・天候・エリア特性で AND 判定する。
    """
    time_band: Optional[TimeOfDay] = None
    preferred_weather: Optional[FrozenSet[WeatherTypeEnum]] = None  # 許容する天候。None で無視
    required_area_traits: Optional[FrozenSet[str]] = None  # 必要なエリア特性ID。None で無視

    def is_satisfied_at(self, time_of_day: TimeOfDay) -> bool:
        """
        指定の時間帯で条件を満たすかどうかを返す。
        preferred_weather / required_area_traits は考慮しない（後方互換）。
        """
        if self.time_band is None:
            return True
        return time_of_day == self.time_band

    def is_satisfied(
        self,
        time_of_day: TimeOfDay,
        weather_type: Optional[WeatherTypeEnum] = None,
        area_traits: Optional[Set[str]] = None,
    ) -> bool:
        """
        時間帯・天候・エリア特性で条件を満たすかどうかを返す。
        time_band AND preferred_weather AND required_area_traits。
        """
        if self.time_band is not None and time_of_day != self.time_band:
            return False
        if self.preferred_weather is not None and len(self.preferred_weather) > 0:
            if weather_type is None or weather_type not in self.preferred_weather:
                return False
        if self.required_area_traits is not None and len(self.required_area_traits) > 0:
            if area_traits is None or not self.required_area_traits.issubset(area_traits):
                return False
        return True
