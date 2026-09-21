
from typing import Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.repository.weather_zone_repository import WeatherZoneRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    RepositoryUnitOfWorkPort,
)

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryWeatherZoneRepository(WeatherZoneRepository, InMemoryRepositoryBase):
    """天候ゾーンリポジトリのインメモリ実装"""

    def __init__(self, data_store: InMemoryDataStore | None = None, unit_of_work: RepositoryUnitOfWorkPort | None = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _zones(self) -> dict[WeatherZoneId, WeatherZone]:
        return self._data_store.weather_zones

    def save(self, weather_zone: WeatherZone) -> WeatherZone:
        cloned_zone = self._clone(weather_zone)
        def operation() -> Any:
            self._zones[cloned_zone.zone_id] = cloned_zone
            return cloned_zone

        self._register_pending_if_uow(weather_zone.zone_id, weather_zone)
        result_value: WeatherZone = self._execute_operation(operation)
        return result_value

    def find_by_id(self, zone_id: WeatherZoneId) -> WeatherZone | None:
        pending = self._get_pending_aggregate(zone_id)
        if pending is not None:
            cloned: WeatherZone | None = self._clone(pending)
            return cloned
        return self._clone(self._zones.get(zone_id))

    def find_by_ids(self, zone_ids: list[WeatherZoneId]) -> list[WeatherZone]:
        return [self._clone(self._zones[zid]) for zid in zone_ids if zid in self._zones]

    def find_by_spot_id(self, spot_id: SpotId) -> WeatherZone | None:
        # 全てのゾーンを走査してスポットが含まれるものを探す
        target_sid_int = int(spot_id)
        for zone in self._zones.values():
            # spot_ids の中身を int で比較
            if any(int(sid) == target_sid_int for sid in zone.spot_ids):
                return self._clone(zone)
        return None

    def find_all(self) -> list[WeatherZone]:
        return [self._clone(zone) for zone in self._zones.values()]

    def delete(self, zone_id: WeatherZoneId) -> bool:
        def operation() -> bool:
            if zone_id in self._zones:
                del self._zones[zone_id]
                return True
            return False
            
        return self._execute_operation(operation)
