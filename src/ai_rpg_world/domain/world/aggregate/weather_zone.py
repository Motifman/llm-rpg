from typing import List, Set
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.weather_zone_name import WeatherZoneName
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.event.weather_events import WeatherChangedEvent
from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
from ai_rpg_world.domain.world.exception.weather_exception import (
    WeatherDomainException,
    WeatherZoneSpotNotFoundException
)


class InvalidWeatherTransitionException(WeatherDomainException):
    """許可されていない天候遷移の例外"""
    error_code = "WEATHER.INVALID_TRANSITION"


class WeatherZone(AggregateRoot):
    """
    天候ゾーンの集約。
    特定のスポットの集まりに対して共通の天候を管理する。
    """
    
    def __init__(
        self,
        zone_id: WeatherZoneId,
        name: WeatherZoneName,
        spot_ids: Set[SpotId],
        current_state: WeatherState
    ):
        super().__init__()
        self._zone_id = zone_id
        self._name = name
        self._spot_ids = set(spot_ids)
        self._current_state = current_state

    @classmethod
    def create(
        cls,
        zone_id: WeatherZoneId,
        name: WeatherZoneName,
        spot_ids: Set[SpotId],
        current_state: WeatherState
    ) -> "WeatherZone":
        return cls(zone_id, name, spot_ids, current_state)

    @property
    def zone_id(self) -> WeatherZoneId:
        return self._zone_id

    @property
    def name(self) -> WeatherZoneName:
        return self._name

    @property
    def spot_ids(self) -> Set[SpotId]:
        return set(self._spot_ids)

    @property
    def current_state(self) -> WeatherState:
        return self._current_state

    def change_weather(self, new_state: WeatherState, force: bool = False):
        """天候を変更し、イベントを発行する"""
        if self._current_state == new_state:
            return

        # 遷移の制約チェック
        if not force and not WeatherSimulationService.is_transition_allowed(
            self._current_state.weather_type, 
            new_state.weather_type
        ):
            raise InvalidWeatherTransitionException(
                f"Transition from {self._current_state.weather_type} to {new_state.weather_type} is not allowed"
            )

        old_weather = self._current_state.weather_type
        self._current_state = new_state

        self.add_event(WeatherChangedEvent.create(
            aggregate_id=self._zone_id,
            aggregate_type="WeatherZone",
            zone_id=self._zone_id,
            old_weather=old_weather,
            new_weather=new_state.weather_type,
            intensity=new_state.intensity
        ))

    def contains_spot(self, spot_id: SpotId) -> bool:
        """指定されたスポットがこの天候ゾーンに含まれるか判定する"""
        return spot_id in self._spot_ids

    def add_spot(self, spot_id: SpotId):
        """ゾーンにスポットを追加する"""
        self._spot_ids.add(spot_id)

    def remove_spot(self, spot_id: SpotId):
        """ゾーンからスポットを削除する"""
        if spot_id not in self._spot_ids:
            raise WeatherZoneSpotNotFoundException(f"Spot {spot_id} not found in weather zone {self._zone_id}")
        self._spot_ids.remove(spot_id)
